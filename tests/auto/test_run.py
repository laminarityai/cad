from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
from mcp import Client
from mcp.server import MCPServer

from cad.auto.log import run_dir
from cad.auto.model import AccountLimit, NeedsPerson, Running, Stopped
from cad.briefs.store import read_brief
from cad.conversations import store
from cad.conversations.model import Mode
from cad.operations.auto import StartInput, auto_start
from cad.operations.registry import OPERATIONS
from cad.operations.tools import tools
from cad.records import signed
from cad.sandbox.image import BUILD, image_tag
from cad.variants import entry

if TYPE_CHECKING:
    from auto.conftest import Session

pytestmark = pytest.mark.anyio

NO_DOCKER: Final = "unix:///nonexistent/docker.sock"
PLATE: Final = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
TEXT: Final = "A plate under 150 g"
UNDER_150: Final = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}
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


async def running(s: Session) -> tuple[str, str]:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    run = await s.start(brief_id=brief_id, material_key="prusament-pla")
    assert isinstance(run.state, Running)
    return brief_id, run.run_id


def records(s: Session, run_id: str) -> int:
    return len(list(run_dir(s.roots, run_id).glob("*.signed")))


async def refused_everything(s: Session, brief_id: str, run_id: str, code: str) -> None:
    score = {"variant_id": "0" * 16, "material_key": "prusament-pla", "brief_id": brief_id}
    for _ in range(3):
        for text in (
            await s.refusal("auto_revise", run_id=run_id, code=code),
            await s.refusal("build_variant", code=code, brief_id=brief_id),
            await s.refusal("score_variant", **score),
        ):
            assert f"RunStopped: auto run {run_id} has stopped" in text, text


async def test_the_auto_operations_are_agent_tools(s: Session) -> None:
    names = {tool.name for tool in (await s.client.list_tools()).tools}
    assert {"auto_start", "auto_revise", "auto_ask"} <= names


@pytest.mark.parametrize("mode", [None, Mode.PLAN, Mode.DESIGN, Mode.TEST])
async def test_auto_start_is_refused_outside_an_auto_mode_conversation(
    s: Session, mode: Mode | None
) -> None:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    if mode is None:
        served = tools(lambda: s.tenant, OPERATIONS)
    else:
        store.set_mode(s.tenant, s.conversation, mode)
        served = tools(lambda: s.bound, OPERATIONS)
    async with Client(MCPServer("cad", tools=served)) as client:
        result = await client.call_tool(
            "auto_start", {"brief_id": brief_id, "material_key": "prusament-pla"}
        )
    assert result.is_error
    text = result.content[0].model_dump()["text"]
    assert "auto_start needs a web app conversation the person switched to Auto mode" in text
    project = read_brief(s.roots, brief_id).project
    assert not (s.roots.projects / project / "auto").exists()


async def test_two_concurrent_starts_of_one_brief_make_one_run(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    both_at_create = threading.Barrier(2, timeout=5)
    create_entry = signed.create_entry

    def racing(*arguments: Any) -> bool:
        both_at_create.wait()
        return create_entry(*arguments)

    monkeypatch.setattr(signed, "create_entry", racing)
    arguments = StartInput(brief_id=brief_id, material_key="prusament-pla")
    with ThreadPoolExecutor(2) as pool:
        racers = [pool.submit(auto_start, s.bound, arguments) for _ in range(2)]
        runs = [racer.result() for racer in racers]
    [run_id] = {run.run_id for run in runs}
    assert all(isinstance(run.state, Running) for run in runs)
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
    assert bounds.statement.startswith("min_mass 50 g > density(prusament-pla) 1.24 g/cm³")
    assert bounds.statement.endswith("envelope 8 cm³ = 9.92 g")
    assert bounds.statement in run.state.report
    await refused_everything(s, brief_id, run.run_id, PLATE)
    assert s.meter.asked == []
    assert not s.tenant.variants.exists()


async def test_proposing_requirements_under_a_run_stops_it(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, run_id = await running(s)
    await s.propose(brief_id, UNDER_150)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id)
    assert "New requirements were proposed, and only the person can confirm them" in text
    stopped = s.run(run_id)
    assert isinstance(stopped.state, Stopped)
    reason = stopped.state.reason
    assert isinstance(reason, NeedsPerson) and reason.why == "proposes_requirements"
    assert s.meter.asked == []


async def test_auto_ask_stops_the_run_with_the_agents_note_and_nothing_spends_after(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, run_id = await running(s)
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
    again = await s.call("auto_ask", run_id=run_id, note="a second note")
    assert again == asked
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    await refused_everything(s, brief_id, run_id, PLATE)
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
    await refused_everything(s, brief_id, run_id, PLATE)
    assert s.meter.asked == ["build"]


async def test_a_check_the_account_limit_refuses_stops_the_run(s: Session) -> None:
    brief_id, run_id = await running(s)
    built = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    s.meter.spent = True
    score = {"variant_id": built["variant_id"], "material_key": "prusament-pla"}
    text = await s.refusal("score_variant", brief_id=brief_id, **score)
    assert f"RunStopped: auto run {run_id} has stopped" in text
    run = s.run(run_id)
    assert isinstance(run.state, Stopped)
    reason = run.state.reason
    assert isinstance(reason, AccountLimit) and reason.refused == built["variant_id"]
    assert s.meter.asked == ["build", "check"]


async def test_a_build_the_account_limit_refuses_for_an_outside_client_stops_no_run(
    s: Session, started: list[str]
) -> None:
    s.meter.spent = True
    brief_id, run_id = await running(s)
    async with Client(MCPServer("cad", tools=tools(lambda: s.tenant, OPERATIONS))) as outside:
        result = await outside.call_tool("build_variant", {"code": PLATE, "brief_id": brief_id})
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
    other = await s.confirmed(TEXT, UNDER_150)
    text = await s.refusal("build_variant", code=PLATE, brief_id=other)
    assert f"RunRefused: auto run {run_id} builds and scores only for brief" in text
    assert s.meter.asked == []


async def test_starting_a_brief_with_a_live_run_returns_that_run(s: Session) -> None:
    brief_id, run_id = await running(s)
    again = await s.start(brief_id=brief_id, material_key="prusament-pla")
    assert again.run_id == run_id


async def test_starting_a_brief_whose_run_stopped_starts_a_new_run(s: Session) -> None:
    brief_id, run_id = await running(s)
    await s.call("auto_ask", run_id=run_id, note="stuck")
    again = await s.start(brief_id=brief_id, material_key="prusament-pla")
    assert again.run_id != run_id
    assert isinstance(again.state, Running)


async def test_a_revision_that_passes_every_checked_requirement_stops_the_run(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, run_id = await running(s)
    done = await s.call("auto_revise", run_id=run_id, code=PLATE)
    while done["settling"]:
        done = await s.call("auto_revise", run_id=run_id, code=PLATE)
    assert done["state"]["reason"] == {"kind": "all_pass", "researched": [], "unverified": []}
    assert "Every checked requirement passes." in done["state"]["report"]
    assert s.meter.asked.count("build") == 1
    asked = list(s.meter.asked)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    await refused_everything(s, brief_id, run_id, PLATE + "\n# thicker\n")
    assert s.meter.asked == asked
