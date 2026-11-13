"""A row that waits on the person shows the agent's proposal beside the check's measure, and a row
the agent assumed shows its assumption beside the measure. Each number traces to the brief store
record or the result that holds it, and the agent's own number is never a confirmation."""

from pathlib import Path

from chain import AssumedStep, CheckStep, ProposedStep, Resolved, Unresolved
from trace_store import SPEC_BY_ID

from cad.briefs import assumptions
from cad.briefs import store as briefs
from cad.briefs.assumptions import Assumption
from cad.briefs.words import describe
from cad.checks.result import Measure
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.scorecard import assumed, awaiting, material
from cad.scorecard.material import ReportedScorecard
from cad.scorecard.model import AwaitingConfirmation
from cad.tables.materials import UNITS
from tests.support.cards import (
    TARGET,
    drafts,
    genuine_card,
    reasons,
    trace,
    with_result,
)

LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 5, "unit": "oz"}}, "under 5 oz")
HOLES = ({"kind": "fastener_holes", "size": "M5", "fit": "clearance", "count": 2}, "two M5 holes")
MASS = CheckStep("mass", SPEC_BY_ID["mass"].version)
HOLE = CheckStep("holes", SPEC_BY_ID["holes"].version)


def waiting_card(roots: Roots) -> tuple[ReportedScorecard, str]:
    brief_id = briefs.create_brief(
        roots, "a plate under 5 oz with two M5 holes", new_project_id()
    ).id
    briefs.propose(roots, brief_id, drafts(LIGHT, HOLES))
    sizes = tuple(
        Measure(name=f"hole_diameter:{at}", value=UNITS.Quantity(5.5, "mm")) for at in range(2)
    )
    card = with_result(genuine_card(), "holes", measured=sizes)
    card = card.model_copy(update={"basis": AwaitingConfirmation(brief_id=brief_id)})
    reported = material.reported(card, None)
    waiting = briefs.read_state(roots, brief_id).proposals[-1].proposal.requirements
    rows = awaiting.rows(waiting, reported.results)
    return reported.model_copy(update={"awaiting": rows}), brief_id


def outcomes(card: ReportedScorecard, store: Path, label: str) -> list[object]:
    return [one.outcome for one in trace(card, store).numbers if one.label.startswith(label)]


def test_a_proposed_value_traces_to_the_agents_proposal_and_never_to_a_confirmation(
    store: Path, roots: Roots
) -> None:
    card, brief_id = waiting_card(roots)
    [light, holes] = briefs.read_state(roots, brief_id).proposals[-1].proposal.requirements
    proposed = ProposedStep(brief_id, 1, light.id, describe(light))
    assert outcomes(card, store, "awaiting[0].values[0].proposed") == [Resolved((proposed,))]
    band = ProposedStep(brief_id, 1, holes.id, describe(holes))
    for at in ("count", "low", "high"):
        assert outcomes(card, store, f"awaiting[1].holes.{at}") == [Resolved((band,))]
    assert trace(card, store).failures == ()


def test_a_measured_value_traces_to_the_rows_check_result(store: Path, roots: Roots) -> None:
    card, _ = waiting_card(roots)
    assert outcomes(card, store, "awaiting[0].values[0].measured") == [Resolved((MASS,))]
    assert outcomes(card, store, "awaiting[1].holes.measured") == [Resolved((HOLE,))] * 2


def test_a_row_number_no_record_holds_is_unresolved(store: Path, roots: Roots) -> None:
    card, _ = waiting_card(roots)
    data = card.model_dump(mode="json")
    data["awaiting"][0]["values"][0]["proposed"]["magnitude"] = 9
    data["awaiting"][0]["values"][0]["measured"]["magnitude"] = 9
    data["awaiting"][1]["holes"]["high"]["magnitude"] = 9
    data["awaiting"][1]["holes"]["measured"][0]["magnitude"] = 9
    changed = ReportedScorecard.model_validate(data)
    assert len(reasons(trace(changed, store), Unresolved, "awaiting")) == 4
    unknown = card.model_copy(
        update={"awaiting": (card.awaiting[0].model_copy(update={"requirement_id": "0" * 16}),)}
    )
    assert reasons(trace(unknown, store), Unresolved, "awaiting[0].values[0].proposed") != []


def test_an_assumed_value_traces_to_the_assumption_in_force(store: Path, roots: Roots) -> None:
    brief_id = briefs.create_brief(roots, "a plate", new_project_id()).id
    target = TARGET.validate_python(LIGHT[0])
    held = assumptions.assume(roots, brief_id, [Assumption(target=target, why="light")], ())
    assert held is not None
    card = genuine_card(basis=AwaitingConfirmation(brief_id=brief_id))
    reported = material.reported(card, None)
    rows = assumed.rows(held.assumptions, reported.results)
    reported = reported.model_copy(update={"assumptions": rows})
    step = AssumedStep(brief_id, held.number, "mass", "")
    assert outcomes(reported, store, "assumptions[0].values[0].assumed") == [Resolved((step,))]
    assert outcomes(reported, store, "assumptions[0].values[0].measured") == [Resolved((MASS,))]
    data = reported.model_dump(mode="json")
    data["assumptions"][0]["values"][0]["assumed"]["magnitude"] = 9
    changed = ReportedScorecard.model_validate(data)
    assert reasons(trace(changed, store), Unresolved, "assumptions") != []
