from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from cad.auto.log import run_dir
from cad.auto.model import AccountLimit, NeedsPerson, Running, Stopped
from cad.checks.jobs import BuildCharge
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
    run = s.person("auto_start", brief_id=brief_id, material_key="prusament-pla")
    assert isinstance(run.state, Running)
    return brief_id, run.run_id


def records(s: Session, run_id: str) -> int:
    return len(list(run_dir(s.roots, run_id).glob("*.signed")))


async def refused_everything(s: Session, brief_id: str, run_id: str, code: str) -> None:
    """A driver that keeps going after the stop: every spending call is refused."""
    score = {"variant_id": "0" * 16, "material_key": "prusament-pla", "brief_id": brief_id}
    for _ in range(3):
        for text in (
            await s.refusal("auto_revise", run_id=run_id, code=code),
            await s.refusal("build_variant", code=code, brief_id=brief_id, auto_run=run_id),
            await s.refusal("score_variant", auto_run=run_id, **score),
        ):
            assert f"RunStopped: auto run {run_id} has stopped" in text, text


async def test_only_the_agents_auto_operations_are_tools(s: Session) -> None:
    names = {tool.name for tool in (await s.client.list_tools()).tools}
    assert {"auto_revise", "auto_ask"} <= names
    assert not {"auto_start", "auto_stop"} & names


async def test_a_conflicting_brief_stops_at_start_with_its_proof_and_builds_nothing(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed(CUBE_TEXT, *CUBE)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    run = s.person("auto_start", brief_id=brief_id)
    assert isinstance(run.state, Stopped)
    reason = run.state.reason
    assert isinstance(reason, NeedsPerson) and reason.why == "conflict"
    [bounds] = reason.bounds
    assert bounds.statement.startswith("min_mass 50 g > density(prusament-pla) 1.24 g/cm³")
    assert bounds.statement.endswith("envelope 8 cm³ = 9.92 g")
    assert bounds.statement in run.state.report
    await refused_everything(s, brief_id, run.run_id, PLATE)
    assert s.meter.charges == []
    assert not s.tenant.variants.exists()


async def test_proposing_requirements_under_a_run_stops_it(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, run_id = await running(s)
    await s.propose(brief_id, UNDER_150)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id, auto_run=run_id)
    assert "New requirements were proposed, and only the person can confirm them" in text
    stopped = s.person("auto_stop", run_id=run_id)
    assert isinstance(stopped.state, Stopped)
    reason = stopped.state.reason
    assert isinstance(reason, NeedsPerson) and reason.why == "proposes_requirements"
    assert s.meter.charges == []


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
    assert s.meter.charges == []
    assert records(s, run_id) == 2


async def test_a_refused_build_stops_the_run_at_the_account_limit(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.meter.refuse = "the account's daily build limit is used up"
    brief_id, run_id = await running(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("auto_revise", run_id=run_id, code=PLATE)
    assert "the account's daily build limit is used up" in text
    vid = entry.variant_id(PLATE, image_tag(BUILD))
    assert s.meter.charges == [BuildCharge(vid)]
    run = s.person("auto_stop", run_id=run_id)
    assert isinstance(run.state, Stopped)
    assert run.state.reason == AccountLimit(
        refused=vid, reason="the account's daily build limit is used up"
    )
    await refused_everything(s, brief_id, run_id, PLATE)
    assert len(s.meter.charges) == 1


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
    assert s.meter.charges == []


async def test_a_run_builds_only_for_its_own_brief(s: Session) -> None:
    _, run_id = await running(s)
    other = await s.confirmed(TEXT, UNDER_150)
    text = await s.refusal("build_variant", code=PLATE, brief_id=other, auto_run=run_id)
    assert f"RunRefused: auto run {run_id} builds and scores only for brief" in text
    assert s.meter.charges == []


async def test_starting_a_brief_with_a_live_run_returns_that_run(s: Session) -> None:
    brief_id, run_id = await running(s)
    again = s.person("auto_start", brief_id=brief_id, material_key="prusament-pla")
    assert again.run_id == run_id


async def test_a_revision_that_passes_every_checked_requirement_stops_the_run(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, run_id = await running(s)
    done = await s.call("auto_revise", run_id=run_id, code=PLATE)
    while done["state"]["kind"] == "running" and done["state"]["settling"]:
        done = await s.call("auto_revise", run_id=run_id, code=PLATE)
    assert done["state"]["reason"] == {"kind": "all_pass", "researched": [], "unverified": []}
    assert "Every checked requirement passes." in done["state"]["report"]
    assert s.meter.charges == [BuildCharge(entry.variant_id(PLATE, image_tag(BUILD)))]
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    await refused_everything(s, brief_id, run_id, PLATE + "\n# thicker\n")
    assert len(s.meter.charges) == 1
