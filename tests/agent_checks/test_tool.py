"""write_check as an MCP client calls it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cad.agent_checks import store
from cad.briefs import store as briefs
from tests.support.agent_checks import fetching, snap_fit

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = pytest.mark.anyio

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
    assert "decides nothing until the person approves it" in written["next_step"]


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
