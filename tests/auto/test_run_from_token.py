from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from mcp import Client
from mcp.server import MCPServer

from cad.auto.model import Running, Stopped, StoppedByPerson
from cad.conversations import store
from cad.conversations.model import ConversationId, Mode
from cad.operations.registry import OPERATIONS
from cad.operations.tools import tools

if TYPE_CHECKING:
    from auto.conftest import Session

pytestmark = pytest.mark.anyio

PLATE: Final = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
TEXT: Final = "A plate under 150 g"
UNDER_150: Final = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}
PLAN_REFUSAL: Final = "build_variant is refused in Plan mode"


async def running(s: Session) -> tuple[str, str]:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    run = await s.start(brief_id=brief_id, material_key="prusament-pla")
    assert isinstance(run.state, Running)
    return brief_id, run.run_id


async def refusal_in(s: Session, cid: ConversationId, tool: str, **arguments: object) -> str:
    served = tools(lambda: store.bind(s.tenant, cid), OPERATIONS)
    async with Client(MCPServer("cad", tools=served)) as client:
        result = await client.call_tool(tool, dict(arguments))
    assert result.is_error, result.structured_content
    return result.content[0].model_dump()["text"]


async def test_the_conversations_run_gates_a_build_and_a_stopped_run_starts_nothing(
    s: Session, started: list[str]
) -> None:
    brief_id, run_id = await running(s)
    store.set_mode(s.tenant, s.conversation, Mode.AUTO)
    stopped = await s.call("auto_ask", run_id=run_id, note="stuck")
    assert stopped["state"]["kind"] == "stopped"
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id)
    assert f"RunStopped: auto run {run_id} has stopped" in text
    assert (started, s.meter.asked) == ([], [])


async def test_a_build_under_the_conversations_run_is_charged_once(s: Session) -> None:
    brief_id, run_id = await running(s)
    await s.call("build_variant", code=PLATE, brief_id=brief_id)
    assert s.meter.asked == ["build"]
    await s.call("build_variant", code=PLATE, brief_id=brief_id)
    assert s.meter.asked == ["build"]
    assert isinstance(s.run(run_id).state, Running)


async def test_the_person_leaving_auto_stops_the_next_build(s: Session, started: list[str]) -> None:
    _, run_id = await running(s)
    store.set_mode(s.tenant, s.conversation, Mode.DESIGN)
    run = s.run(run_id)
    assert isinstance(run.state, Stopped)
    assert isinstance(run.state.reason, StoppedByPerson)
    await s.call("auto_ask", run_id=run_id, note="ignored: the run already stopped")
    assert s.run(run_id) == run
    assert (started, s.meter.asked) == ([], [])


async def test_build_variant_is_refused_in_plan_mode_before_anything_starts(
    s: Session, started: list[str]
) -> None:
    store.set_mode(s.tenant, s.conversation, Mode.PLAN)
    text = await s.refusal("build_variant", code=PLATE)
    assert PLAN_REFUSAL in text
    assert (started, s.meter.asked) == ([], [])


async def test_build_variant_in_design_mode_reaches_the_sandbox(
    s: Session, started: list[str]
) -> None:
    store.set_mode(s.tenant, s.conversation, Mode.DESIGN)
    text = await s.refusal("build_variant", code=PLATE)
    assert "this test starts no container" in text
    assert (len(started), s.meter.asked) == (1, ["build"])


async def test_two_conversations_of_one_account_never_leak_a_mode(
    s: Session, started: list[str]
) -> None:
    planning, designing = ConversationId("c-plan"), ConversationId("c-design")
    store.set_mode(s.tenant, planning, Mode.PLAN)
    store.set_mode(s.tenant, designing, Mode.DESIGN)
    for round_ in range(5):
        in_plan = await refusal_in(s, planning, "build_variant", code=PLATE)
        in_design = await refusal_in(s, designing, "build_variant", code=PLATE + f"# {round_}\n")
        assert PLAN_REFUSAL in in_plan
        assert PLAN_REFUSAL not in in_design
    assert (len(started), s.meter.asked) == (5, ["build"] * 5)
    assert (s.tenant.mode, s.tenant.conversation, s.tenant.auto_run) == (None, None, None)


async def test_auto_mode_with_no_run_refuses_a_build_and_a_score(
    s: Session, started: list[str]
) -> None:
    fresh = ConversationId("c-fresh")
    store.set_mode(s.tenant, fresh, Mode.AUTO)
    score = {"variant_id": "0" * 16, "material_key": "prusament-pla"}
    for text in (
        await refusal_in(s, fresh, "build_variant", code=PLATE),
        await refusal_in(s, fresh, "score_variant", **score),
    ):
        assert "this conversation is in Auto mode, so call auto_start first" in text
    assert (started, s.meter.asked) == ([], [])


async def test_build_variant_takes_no_auto_run_argument(s: Session) -> None:
    text = await s.refusal("build_variant", code=PLATE, auto_run="p-0000000000000000-r0")
    assert "Extra inputs are not permitted" in text
    text = await s.refusal(
        "score_variant", variant_id="0" * 16, material_key="prusament-pla", auto_run="x"
    )
    assert "Extra inputs are not permitted" in text
