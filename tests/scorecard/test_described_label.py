"""Harness case 6, the scorecard: a verdict on a described load case carries the label."""

from typing import Any

from cad.briefs.model import Requirement
from cad.briefs.words import describe
from cad.checks.result import Verdict
from cad.scorecard import requirements
from cad.scorecard.model import PendingCheck
from cad.scorecard.waiting import Waiting
from tests.support.load_cases import hole_hook, shelf
from tests.support.scorecard import SPEC, checked, requirement, result, suite

SHELF = shelf()
FEA = SPEC["fea"]


def safety(load: dict[str, Any]) -> Requirement:
    return requirement({"kind": "min_safety_factor", "load": load, "factor": 2})


def solved(given: Requirement) -> Any:
    found = result("fea", Verdict.PASS, safety_factor=(3.0, "dimensionless"))
    return found.model_copy(update={"instance": requirements.instance(given.target)})


def test_a_verdict_on_a_described_load_case_carries_the_label() -> None:
    given = safety(SHELF)
    judged = checked(requirements.judge(given, (*suite(), solved(given))))
    assert (judged.verdict, judged.load_case) == (Verdict.PASS, "described")
    assert judged.model_dump(mode="json")["load_case"] == "described"


def test_a_verdict_on_a_reviewed_phrase_has_no_label_to_show() -> None:
    given = safety(hole_hook())
    judged = checked(requirements.judge(given, (*suite(), solved(given))))
    assert judged.load_case is None
    assert "load_case" not in judged.model_dump(mode="json", exclude_none=False)


def test_a_waiting_row_on_a_described_load_case_carries_the_label() -> None:
    given = safety(SHELF)
    pending = PendingCheck(
        check_id="fea",
        formula=FEA.formula,
        sources=FEA.sources,
        version=FEA.version,
        instance=requirements.instance(given.target),
    )
    assert requirements.judge(given, (*suite(), pending)) == Waiting(
        requirement_id=given.id,
        statement=describe(given),
        check_id="fea",
        load_case="described",
    )


def test_the_statement_the_person_confirmed_says_what_the_check_ran() -> None:
    assert "pressing into the face" in describe(safety(SHELF))
