"""write_check as an MCP client calls it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cad.agent_checks import store
from cad.briefs import store as briefs
from cad.confirmations import agent_checks as confirming
from cad.projects.model import ProjectId
from tests.support.agent_checks import fetching, snap_fit

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("no_sandbox")]

STRAIN = {
    "target": {"kind": "unchecked", "statement": "the arm flexes at most 2% strain"},
    "quote": "at most 2% strain",
}


async def unchecked(s: Session) -> tuple[str, str]:
    created = await s.call(
        "create_brief", text="A snap-fit catch whose arm flexes at most 2% strain"
    )
    proposed = await s.call(
        "propose_requirements", brief_id=created["brief_id"], requirements=[STRAIN]
    )
    [requirement] = proposed["requirements"]
    return created["brief_id"], requirement["requirement"]["id"]


async def test_write_check_freezes_the_check_and_says_it_decides_nothing_yet(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cad.agent_checks.write.fetch_source", fetching())
    brief_id, requirement_id = await unchecked(s)
    written = await s.call(
        "write_check",
        brief_id=brief_id,
        requirement_id=requirement_id,
        check=snap_fit().model_dump(mode="json"),
    )
    project = briefs.read_brief(s.roots, brief_id).project
    [stored] = store.checks_of(s.roots.projects, project)
    assert written["check_sha256"] == stored.sha256
    assert written["status"] == "stored"
    assert "It decides nothing until they do" in written["next_step"]


async def test_a_refused_check_is_a_named_error_with_the_gates_reason(s: Session) -> None:
    brief_id, requirement_id = await unchecked(s)
    example = {**snap_fit().example.model_dump(), "inputs": {"h": {"value": 2, "unit": "mm"}}}
    bare = snap_fit(formula="h", inputs={"h": "geometry:h"}, sources=[], example=example)
    text = await s.text(
        "write_check",
        brief_id=brief_id,
        requirement_id=requirement_id,
        check=bare.model_dump(mode="json"),
    )
    assert "CheckRefused" in text
    assert "a bare geometry or team measure is not an agent-written check" in text


async def written(s: Session, monkeypatch: pytest.MonkeyPatch) -> tuple[str, ProjectId, str]:
    """A brief with a frozen strain check: its id, its project and the check's sha256."""
    monkeypatch.setattr("cad.agent_checks.write.fetch_source", fetching())
    brief_id, requirement_id = await unchecked(s)
    check = snap_fit().model_dump(mode="json")
    stored = await s.call(
        "write_check", brief_id=brief_id, requirement_id=requirement_id, check=check
    )
    return brief_id, briefs.read_brief(s.roots, brief_id).project, stored["check_sha256"]


def held_to(sha256: str, **changes: object) -> dict[str, object]:
    target = {"kind": "agent_limit", "check_sha256": sha256, "comparator": "at_most"}
    return {
        "target": target | {"limit": {"magnitude": 2, "unit": "%"}} | changes,
        "quote": STRAIN["quote"],
    }


async def test_the_page_asks_the_person_to_approve_the_check_beside_its_requirement(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, project, sha256 = await written(s, monkeypatch)
    await s.call("propose_requirements", brief_id=brief_id, requirements=[held_to(sha256)])
    asked = await s.call("ask_to_confirm", project_id=project)
    assert [(one["kind"], one["outcome"]) for one in asked["items"]] == [
        ("requirements", "waiting"),
        ("agent_check", "waiting"),
    ]
    body = s.get(s.person.url)[1]
    assert confirming.TITLE in body
    assert "Snap arm strain: The strain at the root of the snap arm" in body
    assert "Our team has not reviewed this check." in body
    assert "gives 0.75 %, and the formula gives 0.75 %." in body
    assert s.post(s.person.url, "confirm")[0] == 200
    asked = await s.call("ask_to_confirm", project_id=project)
    assert [one["outcome"] for one in asked["items"]] == ["confirmed", "confirmed"]
    assert asked["items"][1]["check_sha256"] == sha256


async def test_the_check_replaces_its_waiting_unchecked_row_only_when_removed(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, project, sha256 = await written(s, monkeypatch)
    carried = await s.call(
        "propose_requirements", brief_id=brief_id, requirements=[held_to(sha256)]
    )
    assert [row["requirement"]["target"]["kind"] for row in carried["requirements"]] == [
        "unchecked",
        "agent_limit",
    ]
    unchecked_id = carried["requirements"][0]["requirement"]["id"]
    replaced = await s.call("propose_requirements", brief_id=brief_id, remove=[unchecked_id])
    assert [row["requirement"]["target"]["kind"] for row in replaced["requirements"]] == [
        "agent_limit"
    ]
    await s.call("ask_to_confirm", project_id=project)
    assert "Remove:" not in s.get(s.person.url)[1]


async def test_declining_only_the_check_keeps_the_requirements_confirmed(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, project, sha256 = await written(s, monkeypatch)
    await s.call("propose_requirements", brief_id=brief_id, requirements=[held_to(sha256)])
    await s.call("ask_to_confirm", project_id=project)
    note = "that is not where the arm bends"
    assert s.post(s.person.url, "confirm", note, {"decline-1": "decline"})[0] == 200
    [requirements, check] = (await s.call("ask_to_confirm", project_id=project))["items"]
    assert (requirements["outcome"], check["outcome"], check["note"]) == (
        "confirmed",
        "declined",
        note,
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"check_sha256": "0" * 64}, "which project"),
        ({"comparator": "at_least"}, "but the check is at_most"),
        ({"limit": None}, "the check's sources write none"),
        ({"limit": {"magnitude": 2, "unit": "mm"}}, "not a unit like %"),
    ],
    ids=["unknown-check", "comparator", "no-limit", "wrong-unit"],
)
async def test_an_agent_limit_that_does_not_fit_its_check_is_refused(
    s: Session, monkeypatch: pytest.MonkeyPatch, changes: dict[str, object], reason: str
) -> None:
    brief_id, _, sha256 = await written(s, monkeypatch)
    text = await s.text(
        "propose_requirements", brief_id=brief_id, requirements=[held_to(sha256, **changes)]
    )
    assert "BadProposal" in text
    assert reason in text
    [proposal] = briefs.read_state(s.roots, brief_id).proposals
    assert proposal.proposal.number == 1


async def test_a_check_written_for_another_brief_cannot_decide_this_one(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, project, sha256 = await written(s, monkeypatch)
    other = await s.call("create_brief", text="A lid with a catch", project_id=project)
    text = await s.text(
        "propose_requirements",
        brief_id=other["brief_id"],
        requirements=[{**held_to(sha256), "quote": "A lid"}],
    )
    assert "names a check written for brief" in text
