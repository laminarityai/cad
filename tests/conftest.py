import fcntl
import html
import json
import os
import pwd
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, field
from email.message import Message
from pathlib import Path
from typing import Any, Final, Protocol, cast
from urllib.parse import urlencode, urlsplit

import pytest
from mcp import Client

from cad.context_parts.ingest import Facts, NotAPart
from cad.knowledge.corpus import Corpus
from cad.knowledge.search import Index
from cad.records.roots import Roots
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, BuildFailed, Built
from cad.server.app import build_server
from cad.variants import entry

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
RAIL = b"CASCADE Topology V3, a rail\n"
RAIL_FACTS = Facts(solids=1, volume_mm3=6000.0, box_min=(-15, 0, 0), box_max=(15, 20, 10))
NOT_A_PART = b"CASCADE Topology V3, a face and no solid\n"


def fake_ingest(brep: bytes) -> Facts | NotAPart:
    return NotAPart("it has no solid") if brep == NOT_A_PART else RAIL_FACTS


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class _Stay(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


STAY: Final = urllib.request.build_opener(_Stay)
SNAPSHOT: Final = re.compile(r'name="snapshot" value="([^"]*)"')


def exchange(
    url: str, body: bytes | None = None, headers: Mapping[str, str] | None = None
) -> tuple[int, str, Message]:
    sent = urllib.request.Request(url, data=body, headers=dict(headers or {}))
    try:
        with STAY.open(sent, timeout=5) as response:
            return response.status, response.read().decode(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(), error.headers


def request(
    url: str, body: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int, str]:
    return exchange(url, body, headers)[:2]


def form(answer: str, note: str = "", fields: Mapping[str, str] | None = None) -> bytes:
    return urlencode({"answer": answer, "note": note, **(fields or {})}).encode()


def form_headers(url: str, **headers: str) -> dict[str, str]:
    return {
        "Origin": origin_of(url),
        "Content-Type": "application/x-www-form-urlencoded",
        **headers,
    }


@dataclass
class Person:
    """Plays the user in a browser: follows each sign-in link the server hands its opener, keeps
    the session cookie and the snapshot of the page it last saw, and may answer the page."""

    urls: list[str] = field(default_factory=list[str])
    answer: str | None = None
    delay: float = 0.05
    statuses: list[int] = field(default_factory=list[int])
    cookie: str | None = None
    snapshots: dict[str, str] = field(default_factory=dict[str, str])
    sign_ins: list[str] = field(default_factory=list[str])

    def __call__(self, sign_in: str) -> None:
        self.sign_ins.append(sign_in)
        status, _, headers = exchange(sign_in)
        assert status == 303, status
        self.cookie = headers["Set-Cookie"].split(";")[0]
        url = origin_of(sign_in) + headers["Location"]
        self.get(url)
        self.urls.append(url)
        if self.answer is not None:
            threading.Thread(target=self._answer, args=(url, self.answer), daemon=True).start()

    def _answer(self, url: str, answer: str) -> None:
        time.sleep(self.delay)
        self.statuses.append(self.post(url, answer, "make it lighter")[0])

    @property
    def url(self) -> str:
        return self.urls[-1]

    def signed_in(self, headers: Mapping[str, str]) -> dict[str, str]:
        return {**({} if self.cookie is None else {"Cookie": self.cookie}), **headers}

    def get(self, url: str, **headers: str) -> tuple[int, str]:
        status, body = request(url, headers=self.signed_in(headers))
        shown = SNAPSHOT.search(body)
        if shown is not None:
            self.snapshots[url] = html.unescape(shown.group(1))
        return status, body

    def post(
        self,
        url: str,
        answer: str,
        note: str = "",
        fields: dict[str, str] | None = None,
        **headers: str,
    ) -> tuple[int, str]:
        sealed = {"snapshot": self.snapshots[url]} if url in self.snapshots else {}
        body = form(answer, note, {**sealed, **(fields or {})})
        return request(url, body, self.signed_in(form_headers(url, **headers)))


@dataclass(frozen=True)
class Rows:
    text: str = TEXT
    under_150: dict[str, Any] = field(default_factory=lambda: UNDER_150)
    shelf: dict[str, Any] = field(default_factory=lambda: SHELF)
    envelope: dict[str, Any] = field(default_factory=lambda: ENVELOPE)
    solid: dict[str, Any] = field(default_factory=lambda: SOLID)
    rail: bytes = RAIL
    rail_facts: Facts = RAIL_FACTS
    not_a_part: bytes = NOT_A_PART


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
    variants: Path
    rows: Rows = field(default_factory=Rows)
    request = staticmethod(request)

    def get(self, url: str, **headers: str) -> tuple[int, str]:
        return self.person.get(url, **headers)

    def post(
        self,
        url: str,
        answer: str,
        note: str = "",
        fields: dict[str, str] | None = None,
        **headers: str,
    ) -> tuple[int, str]:
        return self.person.post(url, answer, note, fields, **headers)

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

    def variant(self, code: str, brep: bytes | None = RAIL) -> str:
        vid = entry.variant_id(code, image_tag(BUILD))
        built = Build(outcome=Built(), output="")
        failed = Build(outcome=BuildFailed(error="NameError", traceback=""), output="")
        entry.save(self.variants, vid, code, built if brep else failed, brep)
        return vid


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


class MakeCorpus(Protocol):
    def __call__(
        self, files: Mapping[str, str], aliases: Mapping[str, list[str]] | None = None
    ) -> Corpus: ...


class MakeIndex(Protocol):
    def __call__(
        self, files: Mapping[str, str], aliases: Mapping[str, list[str]] | None = None
    ) -> Index: ...
