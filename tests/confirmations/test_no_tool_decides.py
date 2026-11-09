from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from cad.context_parts.store import confirmed_parts
from cad.projects.model import ProjectId

if TYPE_CHECKING:
    from conftest import Proposed, Session

pytestmark = pytest.mark.anyio

FORGED = {"status": "confirmed", "answer": "confirm", "decision": "confirmed", "token": "x"}


def argument_shapes(s: Session, brief: Proposed) -> list[tuple[str, dict[str, Any]]]:
    brief_id, project_id = brief.brief_id, brief.project_id
    every_row = [s.rows.under_150, s.rows.shelf, s.rows.envelope, s.rows.solid]
    part = {"brief_id": brief_id, "quote": "shelf", "name": "shelf", "variant_id": s.variant("")}
    shapes: list[tuple[str, dict[str, Any]]] = [
        ("create_brief", {"text": s.rows.text}),
        ("create_brief", {"text": s.rows.text, "project_id": project_id}),
        ("propose_requirements", {"brief_id": brief_id, "requirements": every_row}),
        ("propose_requirements", {"brief_id": brief_id, "requirements": every_row}),
        ("propose_requirements", {"brief_id": brief_id, "requirements": every_row[:1]}),
        ("ask_to_confirm", {"project_id": project_id}),
        ("ask_to_confirm", {"project_id": project_id}),
        ("list_requirements", {"brief_id": brief_id}),
        ("propose_context_part", part),
        ("propose_context_part", part),
        ("ask_to_confirm", {"project_id": project_id}),
        ("ask_to_confirm", {"project_id": "../" + project_id}),
        ("ask_to_confirm", {"project_id": brief_id}),
    ]
    for row in every_row:
        shapes.append(("propose_requirements", {"brief_id": brief_id, "requirements": [row]}))
        shapes.append(("ask_to_confirm", {"project_id": project_id}))
        forged_row = {**row, **FORGED}
        forged_target = {**row, "target": {**row["target"], **FORGED}}
        for forged in (forged_row, forged_target):
            shapes.append(
                ("propose_requirements", {"brief_id": brief_id, "requirements": [forged]})
            )
    for tool, arguments in list(shapes):
        for name, value in FORGED.items():
            shapes.append((tool, {**arguments, name: value}))
    return shapes


async def test_no_tool_call_with_any_argument_shape_confirms_anything(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    for tool, arguments in argument_shapes(s, brief):
        await s.client.call_tool(tool, arguments)
    decisions = sorted(s.roots.briefs.glob("*/decisions/*"))
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    asked = await s.ask(brief)
    assert decisions == []
    assert not list(s.roots.projects.glob("*/answers"))
    assert confirmed_parts(s.roots.projects, ProjectId(brief.project_id)) == ()
    assert {i["outcome"] for i in asked["items"] if i["kind"] == "context_part"} == {"waiting"}
    assert listed["confirmed_proposal"] is None
    assert {p["status"] for p in listed["proposals"]} <= {"proposed", "superseded"}
    assert not [
        r for p in listed["proposals"] for r in p["requirements"] if r["status"] != "proposed"
    ]


@pytest.mark.parametrize("field", sorted(FORGED))
async def test_a_forged_field_on_a_requirement_row_is_refused_not_ignored(
    s: Session, field: str
) -> None:
    brief_id = await s.call("create_brief", text=s.rows.text)
    result = await s.client.call_tool(
        "propose_requirements",
        {"brief_id": brief_id["brief_id"], "requirements": [{**s.rows.under_150, field: "x"}]},
    )
    assert result.is_error
    assert not list(s.roots.briefs.glob("*/proposals/*"))
