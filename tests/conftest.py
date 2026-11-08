import json
import os
import pwd
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode, urlsplit

import pytest
from mcp import Client

from cad.records.roots import Roots
from cad.server.app import build_server

TEXT = "A wall bracket for a 2 kg shelf, under 150 g, fits in 120 x 80 x 40 mm, printable in PETG"
UNDER_150 = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}
SHELF = {
    "target": {"kind": "unchecked", "statement": "holds a 2 kg shelf"},
    "quote": "for a 2 kg shelf",
}
ENVELOPE = {
    "target": {
        "kind": "envelope",
        "edges": [{"magnitude": edge, "unit": "mm"} for edge in (120, 80, 40)],
    },
    "quote": "fits in 120 x 80 x 40 mm",
}
SOLID = {"target": {"kind": "closed_solid"}, "quote": "printable in PETG"}


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def request(
    url: str, body: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int, str]:
    sent = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(sent, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def get(url: str, **headers: str) -> tuple[int, str]:
    return request(url, headers=headers)


def post(
    url: str, answer: str, note: str = "", fields: dict[str, str] | None = None, **headers: str
) -> tuple[int, str]:
    body = urlencode({"answer": answer, "note": note, **(fields or {})}).encode()
    sent = {
        "Origin": origin_of(url),
        "Content-Type": "application/x-www-form-urlencoded",
        **headers,
    }
    return request(url, body, sent)


@dataclass
class Person:
    """Plays the user: receives each page URL the server opens, and may answer it."""

    urls: list[str] = field(default_factory=list[str])
    answer: str | None = None
    delay: float = 0.05
    statuses: list[int] = field(default_factory=list[int])

    def __call__(self, url: str) -> None:
        self.urls.append(url)
        if self.answer is not None:
            threading.Thread(target=self._answer, args=(url, self.answer), daemon=True).start()

    def _answer(self, url: str, answer: str) -> None:
        time.sleep(self.delay)
        self.statuses.append(post(url, answer, "make it lighter")[0])

    @property
    def url(self) -> str:
        return self.urls[-1]


@dataclass(frozen=True)
class Rows:
    text: str = TEXT
    under_150: dict[str, Any] = field(default_factory=lambda: UNDER_150)
    shelf: dict[str, Any] = field(default_factory=lambda: SHELF)
    envelope: dict[str, Any] = field(default_factory=lambda: ENVELOPE)
    solid: dict[str, Any] = field(default_factory=lambda: SOLID)


@dataclass(frozen=True)
class Proposed:
    brief_id: str
    project_id: str


@dataclass
class Session:
    """An MCP client on an in-process server, and the person's browser (plain HTTP)."""

    client: Client
    person: Person
    roots: Roots
    rows: Rows = field(default_factory=Rows)
    get = staticmethod(get)
    post = staticmethod(post)
    request = staticmethod(request)

    async def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        result = await self.client.call_tool(tool, arguments)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return result.structured_content

    async def text(self, tool: str, **arguments: Any) -> str:
        """Everything a client sees from one call, ok or error."""
        result = await self.client.call_tool(tool, arguments)
        blocks = json.dumps([block.model_dump() for block in result.content])
        return blocks + json.dumps(result.structured_content)

    async def proposed(
        self, *requirements: dict[str, Any], project_id: str | None = None
    ) -> Proposed:
        joined = {} if project_id is None else {"project_id": project_id}
        created = await self.call("create_brief", text=TEXT, **joined)
        brief_id = created["brief_id"]
        await self.call("propose_requirements", brief_id=brief_id, requirements=list(requirements))
        return Proposed(brief_id, created["project_id"])

    async def ask(self, proposed: Proposed) -> dict[str, Any]:
        return await self.call("ask_to_confirm", project_id=proposed.project_id)


@pytest.fixture
def person() -> Person:
    return Person()


@pytest.fixture
async def s(tmp_path: Path, person: Person) -> AsyncIterator[Session]:
    roots = Roots(tmp_path / "briefs", tmp_path / "projects")
    server = build_server(tmp_path / "variants", roots, opener=person, wait_seconds=0.3)
    async with Client(server) as client:
        yield Session(client, person, roots)


# The operator's ~/.cad holds their real briefs, answers and keys. A test that falls back to a
# default root (HOME_ROOTS, VARIANTS_ROOT) would write there, so every write under it fails the
# test. The sandbox stage is the one shared directory tests may write.
GUARDED_HOMES = tuple({Path(pwd.getpwuid(os.getuid()).pw_dir), Path.home()})
GUARDED = tuple(str(home / ".cad") for home in GUARDED_HOMES)
ALLOWED = tuple(f"{cad}{os.sep}stage" for cad in GUARDED)
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
WRITE_EVENTS = frozenset(
    {"os.mkdir", "os.rename", "os.remove", "os.rmdir", "os.link", "os.symlink", "os.chmod"}
    | {"os.truncate", "os.utime", "shutil.rmtree"}
)
home_writes: list[str] = []


def _guarded(target: object) -> str | None:
    if not isinstance(target, str | bytes | os.PathLike):
        return None
    path = os.path.abspath(os.fsdecode(cast("str | bytes | os.PathLike[str]", target)))
    inside = any(path.startswith(cad + os.sep) for cad in GUARDED)
    allowed = any(path == stage or path.startswith(stage + os.sep) for stage in ALLOWED)
    return path if inside and not allowed else None


def _refuse_home_writes(event: str, arguments: tuple[object, ...]) -> None:
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
            home_writes.append(f"{event} {path}")
            raise PermissionError(f"a test wrote to the operator's {path}; give it tmp_path roots")


sys.addaudithook(_refuse_home_writes)


@pytest.fixture(name="home_writes", autouse=True)
def no_write_reaches_the_operators_home() -> Iterator[list[str]]:
    yield home_writes
    written, home_writes[:] = list(home_writes), []
    if written:
        pytest.fail(f"this test wrote to the operator's ~/.cad: {written}")
