from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from conftest import Session

pytestmark = pytest.mark.anyio

SRC = Path(__file__).resolve().parents[2] / "src"
FORGED = {"status": "confirmed", "answer": "confirm", "decision": "confirmed", "token": "x"}


def argument_shapes(s: Session, brief_id: str) -> list[tuple[str, dict[str, Any]]]:
    every_row = [s.rows.under_150, s.rows.shelf, s.rows.envelope, s.rows.solid]
    shapes: list[tuple[str, dict[str, Any]]] = [
        ("create_brief", {"text": s.rows.text}),
        ("propose_requirements", {"brief_id": brief_id, "requirements": every_row}),
        ("propose_requirements", {"brief_id": brief_id, "requirements": every_row}),
        ("propose_requirements", {"brief_id": brief_id, "requirements": every_row[:1]}),
        ("confirm_requirements", {"brief_id": brief_id}),
        ("confirm_requirements", {"brief_id": brief_id}),
        ("list_requirements", {"brief_id": brief_id}),
        ("confirm_requirements", {"brief_id": "../" + brief_id}),
    ]
    for row in every_row:
        shapes.append(("propose_requirements", {"brief_id": brief_id, "requirements": [row]}))
        shapes.append(("confirm_requirements", {"brief_id": brief_id}))
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
    brief_id = await s.proposed(s.rows.under_150)
    for tool, arguments in argument_shapes(s, brief_id):
        await s.client.call_tool(tool, arguments)
    decisions = sorted(s.root.glob("*/decisions/*"))
    listed = await s.call("list_requirements", brief_id=brief_id)
    assert decisions == []
    assert listed["confirmed_proposal"] is None
    assert {p["status"] for p in listed["proposals"]} <= {"proposed", "superseded"}
    assert not [
        r for p in listed["proposals"] for r in p["requirements"] if r["status"] != "proposed"
    ]


def test_only_the_page_writes_a_decision() -> None:
    callers = sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if any(
            isinstance(node, ast.Attribute | ast.Name)
            and "record_decision" in (getattr(node, "attr", None), getattr(node, "id", None))
            for node in ast.walk(ast.parse(path.read_text()))
        )
    )
    assert callers == ["cad/briefs/page.py"]
