from __future__ import annotations

import html
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import pytest
from pydantic import TypeAdapter

from cad.briefs import page, store
from cad.briefs.ballot import Desk, PageUrl
from cad.briefs.model import Decision, Declined, Target

if TYPE_CHECKING:
    from conftest import Person, Session

pytestmark = pytest.mark.anyio


async def test_a_confirm_on_the_page_confirms_the_set_for_tools_and_checks(
    s: Session, person: Person
) -> None:
    person.answer = "confirm"
    brief_id = await s.proposed(s.rows.under_150, s.rows.shelf)
    confirmed = await s.call("confirm_requirements", brief_id=brief_id)
    listed = await s.call("list_requirements", brief_id=brief_id)
    assert person.statuses == [200]
    assert confirmed["answer"]["outcome"] == "confirmed"
    assert [r["plain"] for r in confirmed["answer"]["requirements"]] == [
        "Mass at most 150 g",
        "holds a 2 kg shelf",
    ]
    assert listed["confirmed_proposal"] == 1
    assert listed["proposals"][0]["status"] == "confirmed"
    assert {r["status"] for r in listed["proposals"][0]["requirements"]} == {"confirmed"}
    checked = store.confirmed_requirements(s.root, brief_id)
    assert checked is not None
    assert [r.id for r in checked.requirements] == [
        r["requirement"]["id"] for r in confirmed["answer"]["requirements"]
    ]


async def test_a_decline_carries_the_persons_note_back(s: Session, person: Person) -> None:
    person.answer = "decline"
    brief_id = await s.proposed(s.rows.under_150)
    declined = await s.call("confirm_requirements", brief_id=brief_id)
    listed = await s.call("list_requirements", brief_id=brief_id)
    assert declined["answer"] == {"outcome": "declined", "note": "make it lighter"}
    assert listed["proposals"][0]["status"] == "declined"
    assert listed["confirmed_proposal"] is None


async def test_an_answer_after_the_wait_reaches_the_next_call(s: Session) -> None:
    brief_id = await s.proposed(s.rows.under_150)
    waiting = await s.call("confirm_requirements", brief_id=brief_id)
    assert s.post(s.person.url, "confirm")[0] == 200
    answered = await s.call("confirm_requirements", brief_id=brief_id)
    assert waiting["answer"]["outcome"] == "pending"
    assert "Tell the user" in waiting["answer"]["message"]
    assert answered["answer"]["outcome"] == "confirmed"
    assert len(s.person.urls) == 1


async def test_a_pending_call_reopens_the_same_page(s: Session) -> None:
    brief_id = await s.proposed(s.rows.under_150)
    await s.call("confirm_requirements", brief_id=brief_id)
    await s.call("confirm_requirements", brief_id=brief_id)
    first, second = s.person.urls
    assert first == second


async def test_the_page_shows_the_brief_each_quote_and_its_check(s: Session) -> None:
    every = (s.rows.under_150, s.rows.envelope, s.rows.shelf, s.rows.solid)
    brief_id = await s.proposed(*every)
    await s.call("confirm_requirements", brief_id=brief_id)
    status, body = s.get(s.person.url)
    assert status == 200
    assert html.escape(s.rows.text) in body
    for row in every:
        assert f'<q class="origin">{html.escape(row["quote"])}</q>' in body
    assert "Decided by the mass check" in body
    assert "Fits inside a box of 120 mm x 80 mm x 40 mm" in body
    assert "No reviewed check: unverified" in body


async def test_the_page_escapes_the_brief_text(s: Session) -> None:
    created = await s.call("create_brief", text="<script>x()</script> under 1 g")
    await s.call(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[{"target": {"kind": "closed_solid"}, "quote": "<script>"}],
    )
    await s.call("confirm_requirements", brief_id=created["brief_id"])
    body = s.get(s.person.url)[1]
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


async def test_the_page_refuses_every_request_without_its_live_token(s: Session) -> None:
    brief_id = await s.proposed(s.rows.under_150)
    await s.call("confirm_requirements", brief_id=brief_id)
    url = s.person.url
    base = url.rsplit("/", 1)[0]
    port = urlsplit(url).port
    refused = {
        "no token GET": s.get(base + "/"),
        "no token POST": s.post(base + "/", "confirm"),
        "wrong token GET": s.get(base + "/" + "A" * 43),
        "wrong token POST": s.post(base + "/" + "A" * 43, "confirm"),
        "wrong Host GET": s.get(url, Host=f"localhost:{port}"),
        "wrong Host POST": s.post(url, "confirm", Host=f"evil.example:{port}"),
        "wrong Origin POST": s.post(url, "confirm", Origin="http://evil.example"),
        "null Origin POST": s.post(url, "confirm", Origin="null"),
        "no Origin POST": s.request(
            url, b"answer=confirm", {"Content-Type": "application/x-www-form-urlencoded"}
        ),
    }
    listed = await s.call("list_requirements", brief_id=brief_id)
    assert {name: status for name, (status, _) in refused.items()} == dict.fromkeys(refused, 403)
    assert len({body for _, body in refused.values()}) == 1
    assert listed["proposals"][0]["status"] == "proposed"
    assert s.get(url)[0] == 200


async def test_a_spent_token_opens_nothing(s: Session) -> None:
    brief_id = await s.proposed(s.rows.under_150)
    await s.call("confirm_requirements", brief_id=brief_id)
    url = s.person.url
    assert s.get(url)[0] == 200
    assert s.post(url, "decline", "no")[0] == 200
    replayed = [s.get(url)[0], s.post(url, "confirm")[0]]
    listed = await s.call("list_requirements", brief_id=brief_id)
    assert replayed == [403, 403]
    assert listed["proposals"][0]["status"] == "declined"


async def test_a_malformed_answer_does_not_spend_the_ballot(s: Session) -> None:
    brief_id = await s.proposed(s.rows.under_150)
    await s.call("confirm_requirements", brief_id=brief_id)
    url = s.person.url
    malformed = [
        s.post(url, "yes")[0],
        s.post(url, "confirm", "x" * 9000)[0],
        s.post(url, "confirm", **{"Content-Type": "text/plain"})[0],
    ]
    assert malformed == [400, 413, 400]
    assert s.post(url, "confirm")[0] == 200


async def test_a_newer_proposal_retires_the_old_page(s: Session) -> None:
    brief_id = await s.proposed(s.rows.under_150)
    await s.call("confirm_requirements", brief_id=brief_id)
    old = s.person.url
    await s.call("propose_requirements", brief_id=brief_id, requirements=[s.rows.shelf])
    retired = [s.get(old)[0], s.post(old, "confirm")[0]]
    await s.call("confirm_requirements", brief_id=brief_id)
    listed = await s.call("list_requirements", brief_id=brief_id)
    assert retired == [403, 403]
    assert s.person.url != old
    assert [p["status"] for p in listed["proposals"]] == ["superseded", "proposed"]


async def test_an_answer_another_process_recorded_first_wins(s: Session) -> None:
    brief_id = await s.proposed(s.rows.under_150)
    await s.call("confirm_requirements", brief_id=brief_id)
    state = store.read_state(s.root, brief_id)
    elsewhere = Decision(
        proposal=1,
        brief_sha256=state.brief_sha256,
        proposal_sha256=state.proposals[0].sha256,
        answer=Declined(note="elsewhere"),
        decided_at=state.brief.created_at,
    )
    store.record_decision(s.root, state.brief.id, elsewhere)
    conflict = s.post(s.person.url, "confirm")[0]
    answered = await s.call("confirm_requirements", brief_id=brief_id)
    assert conflict == 409
    assert answered["answer"] == {"outcome": "declined", "note": "elsewhere"}


async def test_an_expired_ballot_is_refused_and_replaced(s: Session, tmp_path: Path) -> None:
    now = [0.0]
    urls: list[PageUrl] = []
    root = tmp_path / "expiring"
    brief = store.create_brief(root, s.rows.text)
    target = TypeAdapter[Target](Target).validate_python(s.rows.under_150["target"])
    store.propose(root, brief.id, [store.Draft(target=target, quote="under 150 g")])
    desk = Desk(root, urls.append, page.serve, wait_seconds=0.01, clock=lambda: now[0])
    await desk.confirm(brief.id)
    now[0] += 31 * 60
    assert s.get(urls[0])[0] == 403
    await desk.confirm(brief.id)
    assert urls[0] != urls[1]
    assert s.get(urls[1])[0] == 200


async def test_no_tool_result_or_log_record_carries_the_token_or_port(
    s: Session, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    brief_id = await s.proposed(s.rows.under_150)
    texts = [await s.text("confirm_requirements", brief_id=brief_id)]
    s.get(s.person.url)
    s.get(s.person.url.rsplit("/", 1)[0] + "/wrong")
    s.post(s.person.url, "confirm")
    s.post(s.person.url, "confirm")
    time.sleep(0.05)
    for tool in ("confirm_requirements", "list_requirements"):
        texts.append(await s.text(tool, brief_id=brief_id))
    texts.append(await s.text("confirm_requirements", brief_id="0" * 15))
    parts = urlsplit(s.person.url)
    secrets = [parts.path.rsplit("/", 1)[1], f":{parts.port}", "127.0.0.1"]
    logged = [record.getMessage() for record in caplog.records]
    assert logged
    for secret in secrets:
        assert not [t for t in texts if secret in t]
        assert not [m for m in logged if secret in m]
