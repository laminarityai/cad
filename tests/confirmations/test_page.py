from __future__ import annotations

import html
import logging
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from cad.briefs import store
from cad.confirmations import answers, page
from cad.confirmations.answers import ItemAnswer, PageAnswer
from cad.projects.model import ProjectId

if TYPE_CHECKING:
    from tests.support.browser import Person
    from tests.support.session import Proposed, Session

pytestmark = pytest.mark.anyio
ROW = "0123456789abcdef"


def answer_files(s: Session, project_id: str) -> list[Path]:
    return sorted((s.roots.projects / project_id / answers.ANSWERS).glob("*"))


def page_form(fields: dict[str, str]) -> bytes:
    return urlencode({"answer": "confirm", "note": "", **fields}).encode()


def form_only(url: str) -> dict[str, str]:
    parts = urlsplit(url)
    return {
        "Origin": f"{parts.scheme}://{parts.netloc}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def cookie(s: Session) -> str:
    assert s.person.cookie is not None
    return s.person.cookie


async def test_the_post_answers_exactly_the_snapshot(s: Session) -> None:
    first = await s.proposed(s.rows.under_150)
    project = first.project_id
    others = [await s.proposed(row, project_id=project) for row in (s.rows.shelf, s.rows.solid)]
    asked = await s.ask(first)
    opened = s.person.url
    body = s.get(opened)[1]
    assert asked["status"] == "pending"
    assert body.count('<section class="item">') == 3
    assert s.post(opened, "confirm", fields={f"edit-7-{ROW}": "x"})[0] == 400
    assert s.get(opened)[0] == 200
    late = await s.proposed(s.rows.envelope, project_id=project)
    assert s.post(opened, "confirm")[0] == 409
    assert answer_files(s, project) == []
    stale = s.person.snapshots[opened]
    await s.ask(first)
    assert s.person.url == opened and s.person.snapshots[opened] != stale
    assert s.get(s.person.url)[1].count('<section class="item">') == 4
    assert s.post(s.person.url, "confirm")[0] == 200
    briefs = [first, *others, late]
    [stored] = answer_files(s, project)
    ledger = answers.read_ledger(s.roots.projects, ProjectId(project))
    [(sha256, answered)] = ledger.answers
    shown = [store.read_state(s.roots, b.brief_id).proposals[-1].ref for b in briefs]
    assert stored.name == "0001.signed"
    assert [a.item for a in answered.answers] == shown
    assert {a.verdict for a in answered.answers} == {"confirmed"}
    for brief in briefs:
        listed = await s.call("list_requirements", brief_id=brief.brief_id)
        confirmed = store.confirmed_requirements(s.roots, brief.brief_id)
        assert listed["confirmed_proposal"] == 1
        assert confirmed is not None and confirmed.decision_sha256 == sha256
    assert {i["outcome"] for i in (await s.ask(first))["items"]} == {"confirmed"}


async def test_a_confirm_on_the_page_confirms_the_set_for_tools_and_checks(
    s: Session, person: Person
) -> None:
    person.answer = "confirm"
    brief = await s.proposed(s.rows.under_150, s.rows.shelf)
    asked = await s.ask(brief)
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    assert person.statuses == [200]
    assert asked["status"] == "answered"
    assert asked["items"] == [
        {
            "kind": "requirements",
            "brief_id": brief.brief_id,
            "proposal": 1,
            "outcome": "confirmed",
            "note": "",
        }
    ]
    assert "build_variant" in asked["next"]
    assert listed["confirmed_proposal"] == 1
    assert {r["status"] for r in listed["proposals"][0]["requirements"]} == {"confirmed"}
    checked = store.confirmed_requirements(s.roots, brief.brief_id)
    assert checked is not None
    assert [r.id for r in checked.requirements] == [
        r["requirement"]["id"] for r in listed["proposals"][0]["requirements"]
    ]


async def test_a_decline_carries_the_persons_note_back(s: Session, person: Person) -> None:
    person.answer = "decline"
    brief = await s.proposed(s.rows.under_150)
    declined = await s.ask(brief)
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    assert [(i["outcome"], i["note"]) for i in declined["items"]] == [
        ("declined", "make it lighter")
    ]
    assert "propose_requirements" in declined["next"]
    assert listed["proposals"][0]["status"] == "declined"
    assert listed["confirmed_proposal"] is None


async def test_a_project_with_nothing_proposed_opens_no_page(s: Session) -> None:
    created = await s.call("create_brief", text=s.rows.text)
    asked = await s.call("ask_to_confirm", project_id=created["project_id"])
    unknown = await s.text("ask_to_confirm", project_id="p-" + "0" * 16)
    assert (asked["status"], asked["items"], s.person.urls) == ("nothing_to_confirm", [], [])
    assert "UnknownProject: no project p-0000000000000000 is stored" in unknown


async def test_an_answer_after_the_wait_reaches_the_next_call(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    waiting = await s.ask(brief)
    assert s.post(s.person.url, "confirm")[0] == 200
    answered = await s.ask(brief)
    assert waiting["status"] == "pending"
    assert waiting["items"][0]["outcome"] == "waiting"
    assert "Tell the user" in waiting["next"]
    assert answered["status"] == "answered"
    assert len(s.person.urls) == 1


async def test_a_pending_call_reopens_the_same_page(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    await s.ask(brief)
    first, second = s.person.urls
    assert first == second


async def test_the_page_shows_the_brief_each_quote_and_its_check(s: Session) -> None:
    every = (s.rows.under_150, s.rows.envelope, s.rows.shelf, s.rows.solid)
    await s.ask(await s.proposed(*every))
    status, body = s.get(s.person.url)
    assert status == 200
    assert "Confirm what the agent proposed" in body
    assert f'<blockquote class="brief">{html.escape(s.rows.text)}</blockquote>' in body
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
    await s.call("ask_to_confirm", project_id=created["project_id"])
    body = s.get(s.person.url)[1]
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


async def test_the_page_refuses_every_request_without_a_session_or_from_another_origin(
    s: Session,
) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    url = s.person.url
    sealed = {"snapshot": s.person.snapshots[url]}
    signed_out = {
        "no session GET": s.request(url),
        "no session POST": s.request(url, page_form(sealed), form_only(url)),
    }
    cross = {
        "wrong Origin POST": s.post(url, "confirm", Origin="http://evil.example"),
        "null Origin POST": s.post(url, "confirm", Origin="null"),
        "no Origin POST": s.request(
            url,
            page_form(sealed),
            {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie(s)},
        ),
    }
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    assert {name: status for name, (status, _) in signed_out.items()} == dict.fromkeys(
        signed_out, 401
    )
    assert {name: status for name, (status, _) in cross.items()} == dict.fromkeys(cross, 403)
    assert len({body for _, body in cross.values()}) == 1
    assert listed["proposals"][0]["status"] == "proposed"
    assert answer_files(s, brief.project_id) == []
    assert s.get(url)[0] == 200


async def test_an_answered_page_shows_nothing_and_takes_no_second_answer(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    url = s.person.url
    assert s.get(url)[0] == 200
    assert s.post(url, "decline", "no")[0] == 200
    replayed = s.post(url, "confirm")[0]
    status, body = s.get(url)
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    assert replayed == 409
    assert (status, "Nothing in this project waits on you." in body) == (200, True)
    assert listed["proposals"][0]["status"] == "declined"
    assert len(answer_files(s, brief.project_id)) == 1


async def test_a_malformed_answer_or_an_edit_leaves_the_page_answerable(s: Session) -> None:
    await s.ask(await s.proposed(s.rows.under_150))
    url = s.person.url
    malformed = [
        s.post(url, "yes")[0],
        s.post(url, "confirm", "x" * 70000)[0],
        s.post(url, "confirm", "", None, **{"Content-Type": "text/plain"})[0],
        s.post(url, "confirm", fields={f"edit-1-{ROW}": "x"})[0],
        s.post(url, "confirm", fields={f"edit-00-{ROW}": "x"})[0],
        s.post(url, "confirm", fields={"slot": "0123456789abcdef/proposal/1"})[0],
    ]
    status, body = s.post(url, "confirm", fields={f"edit-0-{ROW}": "under 100 g"})
    assert malformed == [400, 413, 400, 400, 400, 400]
    assert (status, "This page changed since it opened" in body) == (400, True)
    assert s.post(url, "confirm", fields={f"edit-0-{ROW}": ""})[0] == 200


async def test_a_newer_proposal_retires_the_old_page(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    old = s.person.url
    await s.call("propose_requirements", brief_id=brief.brief_id, requirements=[s.rows.shelf])
    stale = s.post(old, "confirm")[0]
    await s.ask(brief)
    body = s.get(old)[1]
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    assert stale == 409
    assert answer_files(s, brief.project_id) == []
    assert html.escape(s.rows.shelf["quote"]) in body
    assert [p["status"] for p in listed["proposals"]] == ["superseded", "proposed"]


async def test_an_answer_another_process_recorded_first_wins(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    state = store.read_state(s.roots, brief.brief_id)
    project = state.brief.project
    elsewhere = PageAnswer(
        project=project,
        answers=(ItemAnswer(item=state.proposals[0].ref, verdict="declined"),),
        note="elsewhere",
        decided_at=datetime.now(UTC),
    )
    assert answers.append_answer(s.roots.projects, project, elsewhere)
    conflict = s.post(s.person.url, "confirm")
    answered = await s.ask(brief)
    assert conflict == (409, page.plain("This page was already answered.").decode())
    assert [(i["outcome"], i["note"]) for i in answered["items"]] == [("declined", "elsewhere")]
    assert len(answer_files(s, project)) == 1


@pytest.mark.parametrize("tamper", ["edit a byte", "copy from another project"])
async def test_a_tampered_answer_is_refused_naming_no_host_path(s: Session, tamper: str) -> None:
    brief, other = await s.proposed(s.rows.under_150), await s.proposed(s.rows.shelf)
    for each in (brief, other):
        await s.ask(each)
        assert s.post(s.person.url, "confirm")[0] == 200
    [path] = answer_files(s, brief.project_id)
    if tamper == "edit a byte":
        path.write_bytes(path.read_bytes().replace(b"confirmed", b"declined"))
    else:
        shutil.copy(answer_files(s, other.project_id)[0], path)
    text = await s.text("list_requirements", brief_id=brief.brief_id)
    assert f"TamperedProject: project {brief.project_id}" in text
    assert str(s.roots.projects) not in text


async def test_no_tool_result_or_log_record_carries_the_sign_in_token_or_port(
    s: Session, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    brief: Proposed = await s.proposed(s.rows.under_150)
    texts = [await s.text("ask_to_confirm", project_id=brief.project_id)]
    s.get(s.person.url)
    s.request(s.person.url)
    s.post(s.person.url, "confirm")
    s.post(s.person.url, "confirm")
    time.sleep(0.05)
    texts.append(await s.text("ask_to_confirm", project_id=brief.project_id))
    texts.append(await s.text("list_requirements", brief_id=brief.brief_id))
    texts.append(await s.text("ask_to_confirm", project_id="p-" + "0" * 15))
    sign_in = urlsplit(s.person.sign_ins[0])
    [token] = parse_qs(sign_in.query)["token"]
    secrets = [token, f":{sign_in.port}", "127.0.0.1"]
    logged = [record.getMessage() for record in caplog.records]
    assert logged
    for secret in secrets:
        assert not [t for t in texts if secret in t]
        assert not [m for m in logged if secret in m]
