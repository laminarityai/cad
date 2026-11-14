"""A load case may name the one body the stress check solves alone, and one that names none reads
as on trunk."""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from cad.briefs.keys import target_key
from cad.briefs.model import BriefId, Requirement, body_of, requirement_id
from cad.briefs.origins import BriefSpan
from cad.briefs.words import describe
from cad.checks.result import Verdict
from cad.loads.model import LoadCase
from cad.scorecard import requirements
from tests.support.scorecard import TARGET, checked, result, suite

CASES = TypeAdapter(LoadCase)
BRIEF = BriefId("0123456789abcdef")
ORIGIN = BriefSpan(start=0, end=4)
CASE: dict[str, Any] = {
    "support": {"kind": "flat_end"},
    "load": {
        "kind": "far_end",
        "force": {"magnitude": 10, "unit": "N"},
        "direction": {"kind": "any"},
    },
}
TRUNK = ("0fc7ea6a", "c6560ae5", "5133ba0b592fecda")
"""The case's id and unit case, and its safety factor requirement's id, at 7edff29."""


def safety(load: dict[str, Any]) -> Requirement:
    target = TARGET.validate_python({"kind": "min_safety_factor", "load": load, "factor": 2})
    rid = requirement_id(BRIEF, target, ORIGIN)
    return Requirement(id=rid, brief_id=BRIEF, target=target, origin=ORIGIN)


def test_a_load_case_that_names_no_body_keeps_its_ids_and_bytes() -> None:
    case = CASES.validate_python(CASE)
    one = safety(CASE)
    assert (case.id, case.unit_case, one.id) == TRUNK
    assert "body" not in case.wire()
    assert "body" not in one.model_dump_json()
    assert body_of(one.target) is None


def test_the_body_is_in_the_case_s_ids_on_the_wire_and_in_the_words_the_person_confirms() -> None:
    beam, block = (CASES.validate_python({**CASE, "body": name}) for name in ("beam", "block"))
    assert beam.wire().get("body") == "beam"
    assert len({TRUNK[0], beam.id, block.id}) == 3
    assert len({TRUNK[1], beam.unit_case, block.unit_case}) == 3
    one = safety({**CASE, "body": "beam"})
    assert body_of(one.target) == "beam"
    assert describe(one).startswith("beam: safety factor against yield at least 2 with 10 N")


def test_a_brief_holds_one_safety_factor_per_body() -> None:
    keys = {target_key(safety({**CASE, "body": name}).target) for name in ("beam", "block")}
    assert len(keys | {target_key(safety(CASE).target)}) == 3


def test_a_body_name_that_breaks_the_name_rule_is_refused() -> None:
    with pytest.raises(ValidationError):
        CASES.validate_python({**CASE, "body": "Beam"})


def test_a_stress_pass_on_the_case_s_body_is_judged_on_its_own_measures() -> None:
    given = safety({**CASE, "body": "beam"})
    solved = result("fea", Verdict.PASS, safety_factor=(3.0, "dimensionless"))
    found = solved.model_copy(update={"instance": requirements.instance(given.target)})
    judged = checked(requirements.judge(given, (*suite(), found)))
    assert judged.verdict is Verdict.PASS
    assert judged.statement.startswith("beam: ")
