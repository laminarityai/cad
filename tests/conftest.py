import fcntl
import os
import pwd
import sys
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import pytest
from mcp import Client

from cad.records.roots import Roots
from cad.server.app import build_server
from tests.support.browser import Person
from tests.support.rows import fake_ingest
from tests.support.session import Session

pytest_plugins = ("shards",)


@pytest.fixture
def alone_removing_orphans(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """A server start removes exited orphans daemon-wide, so xdist workers take turns here."""
    with (tmp_path_factory.getbasetemp().parent / "removes-orphans.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


@pytest.fixture
def person() -> Person:
    return Person()


@pytest.fixture
def browser() -> type[Person]:
    return Person


@pytest.fixture
async def s(tmp_path: Path, person: Person) -> AsyncIterator[Session]:
    roots = Roots(tmp_path / "briefs", tmp_path / "projects")
    variants = tmp_path / "variants"
    server = build_server(variants, roots, opener=person, wait_seconds=0.3, ingest=fake_ingest)
    async with Client(server) as client:
        yield Session(client, person, roots, variants)


# The operator's ~/.cad holds their real briefs, answers and keys. A test that falls back to a
# default root (HOME_ROOTS, VARIANTS_ROOT) would write there, so every write under it fails the
# test. The sandbox stage is the one shared directory tests may write.
GUARDED_HOMES = tuple({Path(pwd.getpwuid(os.getuid()).pw_dir), Path.home()})
GUARDED = tuple(
    {
        form(str(home / ".cad")).casefold()
        for home in GUARDED_HOMES
        for form in (os.path.abspath, os.path.realpath)
    }
)
ALLOWED = tuple(f"{cad}{os.sep}stage" for cad in GUARDED)
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
WRITE_EVENTS = frozenset(
    {"os.mkdir", "os.rename", "os.remove", "os.rmdir", "os.link", "os.symlink", "os.chmod"}
    | {"os.truncate", "os.utime", "shutil.rmtree"}
)
home_writes: list[str] = []
home_writes_lock = threading.Lock()


def _guarded(target: object) -> str | None:
    if not isinstance(target, str | bytes | os.PathLike):
        return None
    path = os.path.abspath(os.fsdecode(cast("str | bytes | os.PathLike[str]", target)))
    for form in {path.casefold(), os.path.realpath(path).casefold()}:
        inside = any(form.startswith(cad + os.sep) for cad in GUARDED)
        allowed = any(form == stage or form.startswith(stage + os.sep) for stage in ALLOWED)
        if inside and not allowed:
            return path
    return None


def _refuse_home_writes(event: str, arguments: tuple[object, ...]) -> None:
    """Refuse a write under the operator's ~/.cad, also through a symlink or in another case.

    It sees only the audited calls of this interpreter. It misses a write from a subprocess or a
    container, a write sqlite3 makes, and an `os.open` with `dir_fd` and a relative name.
    """
    if event == "open":
        mode, flags = arguments[1], arguments[2]
        writes = (isinstance(mode, str) and mode.strip("rbt") != "") or (
            isinstance(flags, int) and flags & WRITE_FLAGS
        )
        targets = arguments[:1] if writes else ()
    elif event in WRITE_EVENTS:
        targets = (
            arguments[:2] if event in ("os.rename", "os.link", "os.symlink") else arguments[:1]
        )
    else:
        return
    for target in targets:
        path = _guarded(target)
        if path is not None:
            with home_writes_lock:
                home_writes.append(f"{event} {path}")
            raise PermissionError(f"a test wrote to the operator's {path}; give it tmp_path roots")


sys.addaudithook(_refuse_home_writes)


@pytest.fixture(name="home_writes", autouse=True)
def no_write_reaches_the_operators_home() -> Iterator[list[str]]:
    yield home_writes
    with home_writes_lock:
        written, home_writes[:] = list(home_writes), []
    if written:
        pytest.fail(f"this test wrote to the operator's ~/.cad: {written}")
