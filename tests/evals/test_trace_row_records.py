"""A row with no verdict traces to the brief store record that holds its number: any numbered
assumption set, never edited once stored, since a card shows the set in force when it was scored."""

from pathlib import Path

from chain import AssumedStep, Resolved, Unresolved

from cad.briefs import assumptions
from cad.briefs import store as briefs
from cad.briefs.assumptions import Assumption, AssumptionSet
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.scorecard import assumed, material
from cad.scorecard.material import ReportedScorecard
from cad.scorecard.model import AwaitingConfirmation
from tests.support.cards import TARGET, genuine_card, reasons, trace


def light(ounces: float) -> Assumption:
    target = {"kind": "max_mass", "mass": {"magnitude": ounces, "unit": "oz"}}
    return Assumption(target=TARGET.validate_python(target), why="light")


def assumed_card(brief_id: str, held: AssumptionSet) -> ReportedScorecard:
    reported = material.reported(genuine_card(basis=AwaitingConfirmation(brief_id=brief_id)), None)
    return reported.model_copy(
        update={"assumptions": assumed.rows(held.assumptions, reported.results)}
    )


def test_a_card_scored_under_an_older_assumption_set_traces_to_that_set(
    store: Path, roots: Roots
) -> None:
    brief_id = briefs.create_brief(roots, "a plate", new_project_id()).id
    first = assumptions.assume(roots, brief_id, [light(5)], ())
    assert first is not None
    card = assumed_card(brief_id, first)
    newer = assumptions.assume(roots, brief_id, [light(7)], ())
    assert newer is not None and newer.number == 2
    traced = trace(card, store)
    step = AssumedStep(brief_id, 1, "mass", "")
    assumed_numbers = [one for one in traced.numbers if one.label.endswith(".assumed")]
    assert [one.outcome for one in assumed_numbers] == [Resolved((step,))]
    assert trace(assumed_card(brief_id, newer), store).failures == ()


def test_a_row_no_numbered_set_holds_stays_untraced(store: Path, roots: Roots) -> None:
    brief_id = briefs.create_brief(roots, "a plate", new_project_id()).id
    first = assumptions.assume(roots, brief_id, [light(5)], ())
    assert first is not None
    assumptions.assume(roots, brief_id, [light(7)], ())
    data = assumed_card(brief_id, first).model_dump(mode="json")
    data["assumptions"][0]["values"][0]["assumed"]["magnitude"] = 9
    found = reasons(trace(ReportedScorecard.model_validate(data), store), Unresolved, "assumptions")
    assert found == [f"no assumption set of brief {brief_id} assumes 9 oz for mass"]
