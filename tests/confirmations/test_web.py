from __future__ import annotations

import re
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId
from cad.accounts.tenants import Tenants
from cad.confirmations import answers
from cad.confirmations.waiting import Door, page_address
from cad.confirmations.web import CLERK_CHALLENGES, CLERK_JS, ClerkSignIn, LocalSignIn, SignIn
from cad.projects.model import ProjectId
from cad.server.hosted import build_app

if TYPE_CHECKING:
    from conftest import Person

pytestmark = pytest.mark.anyio
ALICE = AccountId("user_alice")
BOB = AccountId("user_bob")
CLERK_API = "https://clerk.cad.example"
NONCE = re.compile(r"'nonce-([^']+)'")
TEXT = "A wall bracket under 150 g that also holds a 2 kg shelf"
UNDER_150 = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}
SHELF = {
    "target": {"kind": "unchecked", "statement": "holds a 2 kg shelf"},
    "quote": "holds a 2 kg shelf",
}


class _Stay(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


def exchange(url: str, **headers: str) -> tuple[int, Message]:
    sent = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.build_opener(_Stay).open(sent, timeout=5) as response:
            return response.status, response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.headers


@dataclass(frozen=True)
class Hosted:
    base: str
    local: LocalIssuer
    tenants: Tenants

    async def call(self, account: AccountId, tool: str, **arguments: Any) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.local.mint_agent(account)}"}
        async with (
            httpx2.AsyncClient(base_url=self.base, headers=headers) as client,
            Client(streamable_http_client(f"{self.base}/mcp", http_client=client)) as mcp,
        ):
            result = await mcp.call_tool(tool, arguments)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return result.structured_content

    async def proposed(self, account: AccountId, project_id: str | None = None) -> str:
        joined = {} if project_id is None else {"project_id": project_id}
        created = await self.call(account, "create_brief", text=TEXT, **joined)
        requirements = [UNDER_150] if project_id is None else [SHELF]
        brief_id = created["brief_id"]
        await self.call(
            account, "propose_requirements", brief_id=brief_id, requirements=requirements
        )
        return created["project_id"]

    def sign_in(self, account: AccountId, project_id: str) -> str:
        query = urlencode({"token": self.local.mint_person(account), "project": project_id})
        return f"{self.base}/local/sign-in?{query}"

    def answered(self, account: AccountId, project_id: str) -> list[Path]:
        projects = self.tenants.of(account).roots.projects
        return sorted((projects / project_id / answers.ANSWERS).glob("*.signed"))


@pytest.fixture
def hosted(tmp_path: Path) -> Iterator[Hosted]:
    yield from serve(tmp_path, LocalSignIn)


@pytest.fixture
def clerk_page(tmp_path: Path) -> Iterator[Hosted]:
    """Serves the page Clerk signs in to, while the local issuer still mints the session tokens."""
    yield from serve(tmp_path, lambda _: ClerkSignIn(CLERK_API, "pk_test_Y2xlcmsuY2FkLmV4YW1wbGUk"))


def serve(tmp_path: Path, sign_in: Callable[[LocalIssuer], SignIn]) -> Iterator[Hosted]:
    listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listening.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{listening.getsockname()[1]}"
    local = LocalIssuer.open(tmp_path, base)
    door = Door(page_url=page_address(base), wait_seconds=0.3)
    tenants = Tenants(tmp_path / "accounts", 60, door, lambda _: pytest.fail("no part is read"))
    app = build_app(local.issuer(), tenants, sign_in(local))
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, args=([listening],), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the server did not start"
        time.sleep(0.01)
    yield Hosted(base, local, tenants)
    server.should_exit = True
    thread.join(10)


@pytest.fixture
async def alice(hosted: Hosted, browser: type[Person]) -> AsyncIterator[Person]:
    project_id = await hosted.proposed(ALICE)
    signed_in = browser()
    signed_in(hosted.sign_in(ALICE, project_id))
    yield signed_in


def project_of(person: Person) -> str:
    return person.url.split("/")[-2]


async def test_a_signed_in_post_records_the_account_and_session(
    hosted: Hosted, alice: Person
) -> None:
    project_id = project_of(alice)
    status, body = alice.post(alice.url, "confirm")
    ledger = answers.read_ledger(hosted.tenants.of(ALICE).roots.projects, ProjectId(project_id))
    [(_, answered)] = ledger.answers
    assert (status, "Recorded. You confirmed 1" in body) == (200, True)
    assert answered.account == ALICE
    assert answered.session_id is not None and answered.session_id.startswith("sess_")


async def test_a_stale_snapshot_records_nothing(hosted: Hosted, alice: Person) -> None:
    project_id = project_of(alice)
    await hosted.proposed(ALICE, project_id)
    assert alice.post(alice.url, "confirm")[0] == 409
    assert hosted.answered(ALICE, project_id) == []


async def test_a_replayed_post_records_nothing_more(hosted: Hosted, alice: Person) -> None:
    project_id = project_of(alice)
    first = alice.post(alice.url, "confirm")
    replayed = alice.post(alice.url, "confirm")
    assert (first[0], replayed[0]) == (200, 409)
    assert len(hosted.answered(ALICE, project_id)) == 1


async def test_another_account_cannot_answer_with_alices_form(
    hosted: Hosted, alice: Person, browser: type[Person]
) -> None:
    project_id = project_of(alice)
    bob = browser()
    bob(hosted.sign_in(BOB, await hosted.proposed(BOB)))
    bob.snapshots[alice.url] = alice.snapshots[alice.url]
    status, _ = bob.post(alice.url, "confirm")
    assert status == 403
    assert hosted.answered(ALICE, project_id) == []
    assert alice.post(alice.url, "confirm")[0] == 200


async def test_an_agent_token_cannot_open_or_answer_the_page(hosted: Hosted, alice: Person) -> None:
    bearer = f"Bearer {hosted.local.mint_agent(ALICE)}"
    signed_out = type(alice)(snapshots=dict(alice.snapshots))
    opened = signed_out.get(alice.url, Authorization=bearer)
    posted = signed_out.post(alice.url, "confirm", Authorization=bearer)
    assert (opened[0], posted[0]) == (401, 401)
    assert hosted.answered(ALICE, project_of(alice)) == []


@pytest.mark.parametrize("tamper", ["forged", "edited"])
async def test_a_forged_or_edited_snapshot_is_refused(
    hosted: Hosted, alice: Person, tamper: str
) -> None:
    sealed = alice.snapshots[alice.url]
    payload, mac = sealed.split(".")
    altered = "e30." + mac if tamper == "forged" else f"{payload[:-1]}A.{mac}"
    status, _ = alice.post(alice.url, "confirm", fields={"snapshot": altered})
    assert status == 403
    assert hosted.answered(ALICE, project_of(alice)) == []


async def test_a_bad_sign_in_link_sets_no_cookie(hosted: Hosted) -> None:
    project_id = await hosted.proposed(ALICE)
    good = hosted.local.mint_person(ALICE)
    links = {
        "forged token": {"token": "x.y.z", "project": project_id},
        "agent token": {"token": hosted.local.mint_agent(ALICE), "project": project_id},
        "bad project": {"token": good, "project": "../etc"},
    }
    seen = {
        name: exchange(f"{hosted.base}/local/sign-in?{urlencode(query)}")
        for name, query in links.items()
    }
    assert {name: status for name, (status, _) in seen.items()} == {
        "forged token": 401,
        "agent token": 401,
        "bad project": 400,
    }
    assert not [name for name, (_, headers) in seen.items() if headers.get("Set-Cookie")]


async def test_the_page_answers_with_its_security_headers(alice: Person) -> None:
    assert alice.cookie is not None
    status, headers = exchange(alice.url, Cookie=alice.cookie)
    policy = headers["Content-Security-Policy"]
    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert headers["Referrer-Policy"] == "same-origin"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in policy and "form-action 'self'" in policy


async def test_the_local_page_loads_no_script(alice: Person) -> None:
    assert alice.cookie is not None
    status, headers = exchange(alice.url, Cookie=alice.cookie)
    _, body = alice.get(alice.url)
    assert status == 200
    assert "script-src" not in headers["Content-Security-Policy"]
    assert "<script" not in body


async def test_the_hosted_page_loads_pinned_clerk_from_its_frontend_api(
    clerk_page: Hosted, browser: type[Person]
) -> None:
    url = page_of(clerk_page, await clerk_page.proposed(ALICE))
    cookie = f"__session={clerk_page.local.mint_person(ALICE)}"
    status, headers = exchange(url, Cookie=cookie)
    _, body = browser(cookie=cookie).get(url)
    policy = headers["Content-Security-Policy"]
    nonce = NONCE.search(policy)
    assert status == 200 and nonce is not None
    assert policy == (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        f"frame-ancestors 'none'; script-src {CLERK_API} {CLERK_CHALLENGES} "
        f"'nonce-{nonce.group(1)}'; connect-src {CLERK_API} https://*.protect.clerk.com:*; "
        f"img-src {CLERK_API} https://img.clerk.com; worker-src 'self' blob:; "
        f"frame-src {CLERK_API} {CLERK_CHALLENGES}"
    )
    assert "@5.128.1/" in CLERK_JS
    assert f'src="{CLERK_API}{CLERK_JS}"' in body
    [loader, inline] = re.findall(r'<script nonce="([^"]+)"', body)
    assert loader == inline
    assert "getToken({ skipCache: true })" in body
    assert "sessionStorage" in body


@pytest.mark.parametrize("stale", [False, True])
async def test_a_refreshed_session_answers_a_page_opened_before_its_token_expired(
    clerk_page: Hosted, browser: type[Person], stale: bool
) -> None:
    project_id = await clerk_page.proposed(ALICE)
    url = page_of(clerk_page, project_id)
    session = "sess_read_for_a_long_time"
    person = browser(cookie=f"__session={clerk_page.local.mint_person(ALICE, session=session)}")
    assert person.get(url)[0] == 200
    if stale:
        await clerk_page.proposed(ALICE, project_id)
    person.cookie = f"__session={clerk_page.local.mint_person(ALICE, -60, session)}"
    expired = person.post(url, "confirm")[0]
    person.cookie = f"__session={clerk_page.local.mint_person(ALICE, session=session)}"
    refreshed = person.post(url, "confirm")[0]
    assert (expired, refreshed) == (401, 409 if stale else 200)
    assert len(clerk_page.answered(ALICE, project_id)) == (0 if stale else 1)


def page_of(hosted: Hosted, project_id: str) -> str:
    return f"{hosted.base}/projects/{project_id}/confirm"
