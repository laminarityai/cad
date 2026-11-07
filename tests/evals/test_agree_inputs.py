import ast
from typing import Any

import pytest
from inputs import as_result_contract, read_session, stored_attempts

SCRIPT = """from build123d import *

with BuildPart() as p:
    Box(1, 2, 3)

export_step(
    p.part,
    "out.step",
)
print("done")
"""


def test_the_export_step_call_becomes_the_result_assignment() -> None:
    rewritten = as_result_contract(SCRIPT)
    ast.parse(rewritten)
    assert "result = p.part\n" in rewritten
    assert "export_step" not in rewritten
    assert rewritten.endswith('print("done")\n')


def test_a_script_without_the_export_is_refused() -> None:
    with pytest.raises(ValueError, match="export_step"):
        as_result_contract("result = 1\n")


def test_there_are_sixty_final_attempts_and_the_repaired_ones_use_attempt_1() -> None:
    finals = {a.label: a.path.name for a in stored_attempts(None)}
    assert len(finals) == 60
    assert finals["opus/u_bracket/0"] == "attempt1.py"
    assert finals["sonnet/u_bracket/0"] == "attempt1.py"
    assert finals["opus/arm/0"] == "attempt0.py"


def test_attempt_0_of_the_opus_u_bracket_is_the_one_that_dropped_the_fillet() -> None:
    first = {a.label: a for a in stored_attempts(0)}["opus/u_bracket/0"]
    assert "fillet(inner_corners" in first.path.read_text()


def use(name: str, call_id: str, **arguments: str) -> dict[str, Any]:
    block = {"type": "tool_use", "id": call_id, "name": name, "input": arguments}
    return {"type": "assistant", "message": {"content": [block]}}


def answer(call_id: str, is_error: bool = False) -> dict[str, Any]:
    block = {"type": "tool_result", "tool_use_id": call_id, "is_error": is_error}
    return {"type": "user", "message": {"content": [block]}}


def test_the_scored_variant_is_the_last_score_that_did_not_error() -> None:
    events = [
        use("mcp__cad__build_variant", "a"),
        answer("a"),
        use("mcp__cad__score_variant", "b", variant_id="1111111111111111"),
        answer("b"),
        use("mcp__cad__score_variant", "c", variant_id="2222222222222222"),
        answer("c", is_error=True),
        {"type": "result", "total_cost_usd": 0.04},
    ]
    session = read_session(events)
    assert session.scored_variant == "1111111111111111"
    assert session.cost_usd == 0.04
    assert session.tool_calls == (
        "mcp__cad__build_variant",
        "mcp__cad__score_variant",
        "mcp__cad__score_variant",
    )


def test_a_session_that_never_scored_has_no_variant() -> None:
    events = [use("mcp__cad__build_variant", "a"), answer("a")]
    assert read_session(events).scored_variant is None
