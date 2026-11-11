from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from mcp import Client
from mcp.server import MCPServer

from cad.auto.model import Running, RunStopped, Stopped, StoppedByPerson
from cad.conversations import store
from cad.conversations.model import ConversationId, Mode
from cad.operations.registry import OPERATIONS
from cad.operations.tenants import bind
from cad.operations.tools import tools
from cad.operations.variants import BuildVariantInput, build_variant

if TYPE_CHECKING:
    from tests.support.auto_session import Session

pytestmark = pytest.mark.anyio

PLATE: Final = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
TEXT: Final = "A plate under 150 g"
UNDER_150: Final = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}
AUTO_REFUSAL: Final = "this conversation is in Auto mode, so call auto_start first"


async def running(s: Session) -> tuple[str, str]:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    run = await s.start(
        brief_id=brief_id,
        material_key="prusament-pla",
        material_reason="PLA is light and prints easily",
    )
    assert isinstance(run.state, Running)
    return brief_id, run.run_id


async def refusal_in(s: Session, cid: ConversationId, tool: str, **arguments: object) -> str:
    served = tools(lambda: bind(s.tenant, cid), OPERATIONS)
    async with Client(MCPServer("cad", tools=served)) as client:
        result = await client.call_tool(tool, dict(arguments))
    assert result.is_error, result.structured_content
    return result.content[0].model_dump()["text"]


async def test_a_call_bound_before_the_stop_is_refused_and_starts_nothing(
    s: Session, started: list[str]
) -> None:
    brief_id, run_id = await running(s)
    before_the_stop = s.bound
    stopped = await s.call("auto_ask", run_id=run_id, note="stuck")
    assert stopped["state"]["kind"] == "stopped"
    with pytest.raises(RunStopped):
        build_variant(before_the_stop, BuildVariantInput(code=PLATE, brief_id=brief_id))
    assert (started, s.meter.asked) == ([], [])


@pytest.mark.docker
async def test_a_build_under_the_conversations_run_is_charged_once(s: Session) -> None:
    brief_id, run_id = await running(s)
    chosen = {"material_key": "prusament-pla", "material_reason": "PLA prints easily"}
    await s.call("build_variant", code=PLATE, brief_id=brief_id, **chosen)
    assert s.meter.asked == ["build"]
    await s.call("build_variant", code=PLATE, brief_id=brief_id, **chosen)
    assert s.meter.asked == ["build"]
    assert isinstance(s.run(run_id).state, Running)


async def test_the_person_leaving_auto_stops_the_next_build(s: Session, started: list[str]) -> None:
    _, run_id = await running(s)
    store.set_mode(s.tenant.roots, s.tenant.conversations, s.conversation, Mode.DESIGN)
    run = s.run(run_id)
    assert isinstance(run.state, Stopped)
    assert isinstance(run.state.reason, StoppedByPerson)
    text = await s.refusal("auto_ask", run_id=run_id, note="ignored: the run already stopped")
    assert f"RunNotHeld: auto run {run_id} is not" in text
    assert s.run(run_id) == run
    assert (started, s.meter.asked) == ([], [])


async def test_a_conversation_that_never_chose_a_mode_builds_with_nothing_confirmed(
    s: Session, started: list[str]
) -> None:
    fresh = ConversationId("c-fresh")
    store.create(s.tenant.conversations, fresh)
    text = await refusal_in(s, fresh, "build_variant", code=PLATE)
    assert "Plan mode" not in text
    assert AUTO_REFUSAL not in text
    assert (len(started), s.meter.asked) == (1, ["build"])


async def test_build_variant_in_design_mode_reaches_the_sandbox(
    s: Session, started: list[str]
) -> None:
    store.set_mode(s.tenant.roots, s.tenant.conversations, s.conversation, Mode.DESIGN)
    text = await s.refusal("build_variant", code=PLATE)
    assert "this test starts no container" in text
    assert (len(started), s.meter.asked) == (1, ["build"])


async def test_two_conversations_of_one_account_never_leak_a_mode(
    s: Session, started: list[str]
) -> None:
    automatic, designing = ConversationId("c-auto"), ConversationId("c-design")
    store.create(s.tenant.conversations, automatic)
    store.create(s.tenant.conversations, designing)
    store.set_mode(s.tenant.roots, s.tenant.conversations, automatic, Mode.AUTO)
    store.set_mode(s.tenant.roots, s.tenant.conversations, designing, Mode.DESIGN)
    for round_ in range(5):
        in_auto = await refusal_in(s, automatic, "build_variant", code=PLATE)
        in_design = await refusal_in(s, designing, "build_variant", code=PLATE + f"# {round_}\n")
        assert AUTO_REFUSAL in in_auto
        assert AUTO_REFUSAL not in in_design
    assert (len(started), s.meter.asked) == (5, ["build"] * 5)
    assert (s.tenant.mode, s.tenant.conversation, s.tenant.auto_run) == (None, None, None)


async def test_auto_mode_with_no_run_refuses_a_build_and_a_score(
    s: Session, started: list[str]
) -> None:
    fresh = ConversationId("c-fresh")
    store.create(s.tenant.conversations, fresh)
    store.set_mode(s.tenant.roots, s.tenant.conversations, fresh, Mode.AUTO)
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


async def outside(s: Session, tool: str, **arguments: object) -> str:
    async with Client(MCPServer("cad", tools=tools(lambda: s.tenant, OPERATIONS))) as client:
        result = await client.call_tool(tool, dict(arguments))
    assert result.is_error, result.structured_content
    return result.content[0].model_dump()["text"]


async def test_only_the_conversation_that_started_a_run_can_revise_or_ask(
    s: Session, started: list[str]
) -> None:
    _, run_id = await running(s)
    designing = ConversationId("c2")
    store.create(s.tenant.conversations, designing)
    store.set_mode(s.tenant.roots, s.tenant.conversations, designing, Mode.DESIGN)
    revise = {"run_id": run_id, "code": PLATE}
    ask = {"run_id": run_id, "note": "not mine"}
    for text in (
        await refusal_in(s, designing, "auto_revise", **revise),
        await refusal_in(s, designing, "auto_ask", **ask),
        await outside(s, "auto_revise", **revise),
        await outside(s, "auto_ask", **ask),
    ):
        assert f"RunNotHeld: auto run {run_id} is not this conversation's" in text
    assert isinstance(s.run(run_id).state, Running)
    assert (started, s.meter.asked) == ([], [])


async def test_another_auto_conversation_cannot_take_a_running_run_on_its_brief(
    s: Session,
) -> None:
    brief_id, run_id = await running(s)
    third = ConversationId("c3")
    store.create(s.tenant.conversations, third)
    store.set_mode(s.tenant.roots, s.tenant.conversations, third, Mode.AUTO)
    start = {
        "brief_id": brief_id,
        "material_key": "prusament-pla",
        "material_reason": "PLA is light and prints easily",
    }
    text = await refusal_in(s, third, "auto_start", **start)
    assert f"RunNotHeld: brief {brief_id} has Auto run {run_id} in another" in text
    assert store.read(s.tenant.conversations, third).auto_run is None
    store.set_mode(s.tenant.roots, s.tenant.conversations, third, Mode.DESIGN)
    assert isinstance(s.run(run_id).state, Running)
    assert store.read(s.tenant.conversations, s.conversation).auto_run == run_id


async def test_a_run_another_conversation_stopped_leaves_its_brief_free(s: Session) -> None:
    brief_id, run_id = await running(s)
    await s.call("auto_ask", run_id=run_id, note="stuck")
    third = ConversationId("c3")
    store.create(s.tenant.conversations, third)
    store.set_mode(s.tenant.roots, s.tenant.conversations, third, Mode.AUTO)
    served = tools(lambda: bind(s.tenant, third), OPERATIONS)
    async with Client(MCPServer("cad", tools=served)) as client:
        result = await client.call_tool(
            "auto_start",
            {
                "brief_id": brief_id,
                "material_key": "prusament-pla",
                "material_reason": "PLA is light and prints easily",
            },
        )
    assert not result.is_error, result.content
    assert result.structured_content is not None
    fresh = result.structured_content["run_id"]
    assert fresh != run_id
    assert store.read(s.tenant.conversations, third).auto_run == fresh
