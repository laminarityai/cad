from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
from mcp import Client
from mcp.server import MCPServer

from cad.auto.log import run_dir
from cad.auto.model import (
    AccountLimit,
    AutoRun,
    NeedsPerson,
    Running,
    RunNotHeld,
    RunRefused,
    Stopped,
)
from cad.briefs import store as briefs_store
from cad.briefs.store import read_brief
from cad.conversations import store
from cad.conversations.model import ConversationId
from cad.operations import auto as operations_auto
from cad.operations.auto import StartInput, auto_start
from cad.operations.briefs import (
    CreateBriefInput,
    ProposeRequirementsInput,
    create_brief,
    propose_requirements,
)
from cad.operations.registry import OPERATIONS
from cad.operations.tenants import bind
from cad.operations.tools import tools
from cad.sandbox.image import BUILD, image_tag
from cad.variants import entry
from tests.support.auto_session import PLA_CHOICE, TEXT, running
from tests.support.rows import UNDER_150

LIGHTER: Final = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 100, "unit": "g"}},
    "quote": "under 150 g",
}

if TYPE_CHECKING:
    from tests.support.auto_session import Session

pytestmark = pytest.mark.anyio


def lighter(s: Session, brief_id: str) -> dict[str, Any]:
    confirmed = briefs_store.read_state(s.roots, brief_id).confirmed
    assert confirmed is not None
    return {"brief_id": brief_id, "requirements": [LIGHTER], "remove": confirmed.requirement_ids}


NO_DOCKER: Final = "unix:///nonexistent/docker.sock"
PLATE: Final = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
CUBE_TEXT: Final = "A block that fits in a 20 mm cube, PLA, at least 50 g"
CUBE: Final = (
    {
        "target": {"kind": "envelope", "edges": [{"magnitude": 20, "unit": "mm"}] * 3},
        "quote": "fits in a 20 mm cube",
    },
    {"target": {"kind": "made_of", "material": "prusament-pla"}, "quote": "PLA"},
    {
        "target": {"kind": "min_mass", "mass": {"magnitude": 50, "unit": "g"}},
        "quote": "at least 50 g",
    },
)


def records(s: Session, run_id: str) -> int:
    return len(list(run_dir(s.roots, run_id).glob("*.signed")))


async def test_the_auto_operations_are_agent_tools(s: Session) -> None:
    names = {tool.name for tool in (await s.client.list_tools()).tools}
    assert {"auto_start", "auto_revise", "auto_ask"} <= names


async def test_auto_start_is_refused_for_a_caller_with_no_conversation(s: Session) -> None:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    async with Client(MCPServer("cad", tools=tools(lambda: s.tenant, OPERATIONS))) as client:
        result = await client.call_tool("auto_start", {"brief_id": brief_id, **PLA_CHOICE})
    assert result.is_error
    text = result.content[0].model_dump()["text"]
    assert "auto_start needs a web app conversation, and this caller has none" in text
    project = read_brief(s.roots, brief_id).project
    assert not (s.roots.projects / project / "auto").exists()


async def test_auto_start_is_refused_with_nothing_a_check_decides(s: Session) -> None:
    unchecked = {"target": {"kind": "unchecked", "statement": "looks tidy"}, "quote": "tidy"}
    made_of = {"target": {"kind": "made_of", "material": "prusament-pla"}, "quote": "PLA"}
    brief_id = await s.confirmed("A tidy plate in PLA", unchecked, made_of)
    text = await s.refusal("auto_start", brief_id=brief_id, **PLA_CHOICE)
    assert f"brief {brief_id} has no confirmed requirement that a check decides" in text, text
    held = store.read(s.tenant.conversations, s.conversation)
    assert (held.auto_run, held.stopped_run, held.last_run) == (None, None, None)


async def test_auto_start_is_refused_while_a_proposal_waits_for_the_person(s: Session) -> None:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    await s.call("propose_requirements", **lighter(s, brief_id))
    text = await s.refusal("auto_start", brief_id=brief_id, **PLA_CHOICE)
    assert f"a proposal on brief {brief_id} waits for the person" in text, text
    assert store.read(s.tenant.conversations, s.conversation).last_run is None


@pytest.mark.parametrize("read", ["watermark", "confirmed_requirements"])
async def test_a_proposal_that_lands_during_auto_start_never_runs_under_the_run(
    s: Session, monkeypatch: pytest.MonkeyPatch, read: str
) -> None:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    owner = operations_auto if read == "watermark" else briefs_store
    real = getattr(owner, read)
    landed: list[bool] = []

    def then_propose(*arguments: Any) -> Any:
        found = real(*arguments)
        if not landed:
            landed.append(True)
            proposal = ProposeRequirementsInput.model_validate(lighter(s, brief_id))
            propose_requirements(s.bound, proposal)
        return found

    monkeypatch.setattr(owner, read, then_propose)
    arguments = StartInput(brief_id=brief_id, **PLA_CHOICE)
    if read == "watermark":
        with pytest.raises(RunRefused, match="waits for the person"):
            auto_start(s.bound, arguments)
        assert store.read(s.tenant.conversations, s.conversation).last_run is None
        return
    run = auto_start(s.bound, arguments)
    assert isinstance(run.state, Stopped) and isinstance(run.state.reason, NeedsPerson)
    assert run.state.reason.why == "proposes_requirements"
    held = store.read(s.tenant.conversations, s.conversation)
    assert (held.auto_run, held.stopped_run) == (None, run.run_id)


async def test_two_concurrent_starts_of_one_brief_make_one_run(s: Session) -> None:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    arguments = StartInput(brief_id=brief_id, **PLA_CHOICE)
    other = ConversationId("c-other")
    store.create(s.tenant.conversations, other)
    callers = [s.bound, s.bound, bind(s.tenant, other)]
    with ThreadPoolExecutor(3) as pool:
        racers = [(caller, pool.submit(auto_start, caller, arguments)) for caller in callers]
        outcomes = [(caller.conversation, racer.exception()) for caller, racer in racers]
    [run_id] = {racer.result().run_id for _, racer in racers if racer.exception() is None}
    owner = s.run(run_id).state.start.conversation
    for conversation, refused in outcomes:
        assert (conversation == owner) == (refused is None)
        assert refused is None or isinstance(refused, RunNotHeld)
    stored = run_dir(s.roots, run_id).parent.iterdir()
    assert [path.name for path in stored if not path.name.startswith(".")] == [run_id]


async def test_a_conflicting_brief_stops_at_start_with_its_proof_and_builds_nothing(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed(CUBE_TEXT, *CUBE)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    run = await s.start(brief_id=brief_id)
    assert isinstance(run.state, Stopped)
    reason = run.state.reason
    assert isinstance(reason, NeedsPerson) and reason.why == "conflict"
    [bounds] = reason.bounds
    assert bounds.statement.startswith("The mass must be at least 50 g, but Prusament PLA")
    assert bounds.statement.endswith("weighs 9.92 g filling the whole 20 x 20 x 20 mm box (8 cm³)")
    assert bounds.statement in run.state.report
    await s.held(brief_id, run.run_id)
    assert s.meter.asked == []
    assert not s.tenant.variants.exists()


async def test_proposing_requirements_under_a_run_stops_it(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, run_id = await running(s)
    await s.call("propose_requirements", **lighter(s, brief_id))
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id)
    assert "New requirements were proposed, and only the person can confirm them" in text
    stopped = s.run(run_id)
    assert isinstance(stopped.state, Stopped)
    reason = stopped.state.reason
    assert isinstance(reason, NeedsPerson) and reason.why == "proposes_requirements"
    assert s.meter.asked == []
    text = await s.refusal("auto_start", brief_id=brief_id, **PLA_CHOICE)
    assert f"a proposal on brief {brief_id} waits for the person" in text, text
    project = read_brief(s.roots, brief_id).project
    answer = await s.call("ask_to_confirm", project_id=project)
    assert answer["status"] == "answered", answer
    await s.held(brief_id, run_id)


async def test_auto_ask_stops_the_run_with_the_agents_note_and_nothing_spends_after(
    s: Session,
) -> None:
    _, run_id = await running(s)
    note = "Tried four wall thicknesses; the stiffness needs more than 150 g. Relax which one?"
    asked = await s.call("auto_ask", run_id=run_id, note=note)
    assert asked["state"]["reason"] == {
        "kind": "needs_person",
        "why": "agent_asked",
        "requirements": [],
        "bounds": [],
        "note": note,
    }
    assert note in asked["state"]["report"]
    text = await s.refusal("auto_ask", run_id=run_id, note="a second note")
    assert f"RunStopped: auto run {run_id} has stopped" in text
    assert s.run(run_id).state == AutoRun.model_validate(asked).state
    s.person_acts()
    text = await s.refusal("auto_ask", run_id=run_id, note="a third note")
    assert f"RunNotHeld: auto run {run_id} is not this conversation's" in text
    assert s.meter.asked == []
    assert records(s, run_id) == 2


async def test_a_build_the_account_limit_refuses_stops_the_run_and_starts_nothing(
    s: Session, started: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    s.meter.spent = True
    brief_id, run_id = await running(s)
    text = await s.refusal("auto_revise", run_id=run_id, code=PLATE)
    assert "the account limit is reached: 600 of 600 container-seconds" in text
    vid = entry.variant_id(PLATE, image_tag(BUILD))
    run = s.run(run_id)
    assert isinstance(run.state, Stopped)
    reason = run.state.reason
    assert isinstance(reason, AccountLimit) and reason.refused == vid
    assert reason.reason.startswith("the account limit is reached: 600 of 600 container-seconds")
    assert (s.meter.asked, started) == (["build"], [])
    assert entry.read_manifest(s.tenant.variants, vid) is None
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    await s.held(brief_id, run_id)
    assert s.meter.asked == ["build"]


@pytest.mark.docker
async def test_a_check_the_account_limit_refuses_stops_the_run(s: Session) -> None:
    brief_id, run_id = await running(s)
    built = await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA_CHOICE)
    s.meter.spent = True
    score = {"variant_id": built["variant_id"], "material_key": "prusament-pla"}
    text = await s.refusal("score_variant", brief_id=brief_id, **score)
    assert f"RunStopped: auto run {run_id} has stopped" in text
    run = s.run(run_id)
    assert isinstance(run.state, Stopped)
    reason = run.state.reason
    assert isinstance(reason, AccountLimit) and reason.refused == built["variant_id"]
    assert s.meter.asked == ["build", "check"]
    await s.held(brief_id, run_id)


async def test_a_build_the_account_limit_refuses_for_an_outside_client_stops_no_run(
    s: Session, started: list[str]
) -> None:
    s.meter.spent = True
    brief_id, run_id = await running(s)
    async with Client(MCPServer("cad", tools=tools(lambda: s.tenant, OPERATIONS))) as outside:
        result = await outside.call_tool(
            "build_variant", {"code": PLATE, "brief_id": brief_id, **PLA_CHOICE}
        )
    assert result.is_error
    assert "the account limit is reached: 600 of 600 container-seconds" in str(result.content)
    assert isinstance(s.run(run_id).state, Running)
    assert started == []


async def test_a_replayed_revision_appends_nothing_and_builds_nothing(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = "raise NameError('a revision that does not build')"
    vid = s.failed_variant(code)
    _, run_id = await running(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    first = await s.call("auto_revise", run_id=run_id, code=code)
    assert first["state"]["kind"] == "running"
    [standing] = first["state"]["history"]
    assert (standing["variant_id"], standing["built"], standing["marks"]) == (vid, False, [])
    assert records(s, run_id) == 2
    again = await s.call("auto_revise", run_id=run_id, code=code)
    assert again == first
    assert records(s, run_id) == 2
    assert s.meter.asked == []


async def test_a_run_builds_only_for_its_own_brief(s: Session) -> None:
    _, run_id = await running(s)
    elsewhere = create_brief(replace(s.tenant, conversation=None), CreateBriefInput(text=TEXT))
    await s.propose(elsewhere.brief_id, UNDER_150)
    await s.call("ask_to_confirm", project_id=elsewhere.project_id)
    text = await s.refusal("build_variant", code=PLATE, brief_id=elsewhere.brief_id)
    assert f"RunRefused: auto run {run_id} builds and scores only for brief" in text
    assert s.meter.asked == []


async def test_starting_a_brief_with_a_live_run_returns_that_run(s: Session) -> None:
    brief_id, run_id = await running(s)
    again = await s.start(brief_id=brief_id, **PLA_CHOICE)
    assert again.run_id == run_id


async def test_starting_a_brief_whose_run_stopped_starts_a_new_run(s: Session) -> None:
    brief_id, run_id = await running(s)
    await s.call("auto_ask", run_id=run_id, note="stuck")
    s.person_acts()
    again = await s.start(brief_id=brief_id, **PLA_CHOICE)
    assert again.run_id != run_id
    assert isinstance(again.state, Running)


@pytest.mark.docker
async def test_a_revision_that_passes_every_checked_requirement_stops_the_run(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, run_id = await running(s)
    done = await s.call("auto_revise", run_id=run_id, code=PLATE)
    while done["settling"]:
        done = await s.call("auto_revise", run_id=run_id, code=PLATE)
    assert done["state"]["reason"] == {
        "kind": "all_pass",
        "researched": [],
        "unverified": [],
        "agent_checked": [],
    }
    assert "Every checked requirement passes." in done["state"]["report"]
    assert s.meter.asked.count("build") == 1
    asked = list(s.meter.asked)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    await s.held(brief_id, run_id)
    assert s.meter.asked == asked
