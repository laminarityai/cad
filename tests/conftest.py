import fcntl
import os
import pwd
import sys
import threading
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path
from typing import cast

import pytest
from mcp import Client
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.confirmations.waiting import Door
from cad.confirmations.web import LocalSignIn
from cad.context_parts.ingest import ingest
from cad.operations.tenants import Tenants
from cad.records.roots import Roots
from cad.sandbox import container
from cad.server.app import build_server
from cad.server.hosted import build_app
from tests.support.browser import Person, local_pages
from tests.support.hosted import BASE
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
def started(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The name of each container that reached `docker run`."""
    names: list[str] = []

    def attend(name: str, argv: tuple[str, ...], stdin: bytes, wall_seconds: int) -> None:
        del argv, stdin, wall_seconds
        names.append(name)
        raise container.SandboxUnavailable("this test starts no container")

    monkeypatch.setattr(container, "attend", attend)
    return names


@pytest.fixture
def roots(tmp_path: Path) -> Roots:
    return Roots(tmp_path / "briefs", tmp_path / "projects")


@pytest.fixture
def local(tmp_path: Path) -> LocalIssuer:
    return LocalIssuer.open(tmp_path, BASE)


@pytest.fixture
def tenants(tmp_path: Path) -> Tenants:
    """Accounts that never see a confirmation page: the door gives up after 0.3 s."""
    return Tenants(tmp_path / "accounts", 60, Door(wait_seconds=0.3), ingest)


@pytest.fixture
def confirming_tenants(tmp_path: Path, person: Person) -> Tenants:
    """Accounts whose confirmation page opens for `person`, who confirms it."""
    person.answer = "confirm"
    door = Door(open_page=local_pages(person, lambda account: tenants.of(account)), wait_seconds=5)
    tenants = Tenants(tmp_path / "accounts", 600, door, ingest)
    return tenants


@pytest.fixture
async def app(local: LocalIssuer, tenants: Tenants) -> AsyncIterator[Starlette]:
    app = build_app(local.issuer(), tenants, LocalSignIn(local))
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def s(roots: Roots, tmp_path: Path, person: Person) -> AsyncIterator[Session]:
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


DOCKER_STARTS = frozenset({"run", "build"})
container_starts: list[str] = []


def _note_container_starts(event: str, arguments: tuple[object, ...]) -> None:
    if event != "subprocess.Popen" or not isinstance(argv := arguments[1], list | tuple):
        return
    words = [os.fsdecode(cast("str | bytes", word)) for word in cast("Sequence[object]", argv)[:2]]
    if len(words) == 2 and os.path.basename(words[0]) == "docker" and words[1] in DOCKER_STARTS:
        with home_writes_lock:
            container_starts.append(" ".join(words))


sys.addaudithook(_note_container_starts)


@pytest.fixture(autouse=True)
def a_test_that_starts_a_container_is_marked_docker(
    request: pytest.FixtureRequest,
) -> Iterator[None]:
    """A start in a module or session fixture counts against the first test that used it, so
    the whole file needs the mark: run alone, any of its tests would build that fixture."""
    yield
    with home_writes_lock:
        started, container_starts[:] = list(container_starts), []
    if started and request.node.get_closest_marker("docker") is None:
        pytest.fail(
            f"this test ran `{started[0]}`; mark it, or its file, `pytest.mark.docker` so "
            '`-m "not docker"` leaves it out'
        )
