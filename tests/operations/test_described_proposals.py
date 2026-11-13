"""Harness case 5: the result rule for a described load case."""

import json

import pytest

from tests.support.load_cases import DIRECTIONS, LOADS, SUPPORTS, Part, case, hole_hook, shelf
from tests.support.session import Session
from tests.support.stress import (
    brief_of,
    build_into_the_set,
    deflection,
    heavier,
    row,
    store_a_fea_result,
)

pytestmark = pytest.mark.anyio

CLAMPED = case(SUPPORTS["facing"], LOADS["on_opposite"], DIRECTIONS["into"])
HUNG = case(SUPPORTS["each_inner_curve"], LOADS["on_farthest_inner_curve"], DIRECTIONS["away"])
REFUSAL = "reviewed phrase"


async def propose(s: Session, brief_id: str, *rows: Part) -> dict[str, object]:
    return await s.call("propose_requirements", brief_id=brief_id, requirements=list(rows))


async def refused(s: Session, brief_id: str, *rows: Part) -> str:
    return await s.text("propose_requirements", brief_id=brief_id, requirements=list(rows))


async def test_a_described_case_is_accepted_and_may_be_replaced_while_no_result_exists(
    s: Session,
) -> None:
    brief_id = await brief_of(s, row(shelf()))
    listed = await s.call("list_requirements", brief_id=brief_id)
    [waiting] = listed["proposals"][-1]["requirements"]
    again = await s.call(
        "propose_requirements",
        brief_id=brief_id,
        requirements=[row(CLAMPED)],
        remove=[waiting["requirement"]["id"]],
    )
    assert again["proposal"] == 2
    assert "across a gap" in json.dumps(again["requirements"])
    assert "middle of its largest flat face" not in json.dumps(again["requirements"])


async def test_a_described_case_is_accepted_after_variants_exist_and_before_a_result(
    s: Session,
) -> None:
    brief_id = await brief_of(s)
    build_into_the_set(s, brief_id)
    assert (await propose(s, brief_id, row(shelf())))["proposal"] == 1
    assert (await propose(s, brief_id, row(CLAMPED)))["proposal"] == 2


async def test_an_unknown_fea_result_counts_as_a_result(s: Session) -> None:
    brief_id = await brief_of(s, row(shelf()))
    store_a_fea_result(s, build_into_the_set(s, brief_id))
    text = await refused(s, brief_id, row(CLAMPED))
    assert REFUSAL in text and "requirements[0]" in text


async def waiting_id(s: Session, brief_id: str) -> str:
    listed = await s.call("list_requirements", brief_id=brief_id)
    return listed["proposals"][-1]["requirements"][0]["requirement"]["id"]


async def test_the_same_case_with_a_new_force_replaces_the_old_one_after_a_result(
    s: Session,
) -> None:
    brief_id = await brief_of(s, row(shelf()))
    store_a_fea_result(s, build_into_the_set(s, brief_id))
    assert "pass its id in remove" in await refused(s, brief_id, row(heavier()))
    old = await waiting_id(s, brief_id)
    replaced = await s.call(
        "propose_requirements", brief_id=brief_id, requirements=[row(heavier())], remove=[old]
    )
    [one] = replaced["requirements"]
    assert one["requirement"]["target"]["load"]["load"]["force"]["magnitude"] == 98.0


async def test_a_narrower_proposal_keeps_the_described_case_after_a_result(s: Session) -> None:
    brief_id = await brief_of(s, row(shelf()))
    store_a_fea_result(s, build_into_the_set(s, brief_id))
    bracket = {"target": {"kind": "unchecked", "statement": "a shelf bracket"}, "quote": "shelf"}
    kept = await s.call("propose_requirements", brief_id=brief_id, requirements=[bracket])
    assert [one["requirement"]["target"]["kind"] for one in kept["requirements"]] == [
        "min_safety_factor",
        "unchecked",
    ]


async def test_removing_the_described_case_is_refused_after_a_result(s: Session) -> None:
    brief_id = await brief_of(s, row(shelf()))
    store_a_fea_result(s, build_into_the_set(s, brief_id))
    old = await waiting_id(s, brief_id)
    text = await s.text("propose_requirements", brief_id=brief_id, remove=[old])
    assert "leaves out the described load case" in text


async def test_a_reviewed_phrase_is_accepted_after_a_result_when_the_case_is_kept(
    s: Session,
) -> None:
    brief_id = await brief_of(s, row(shelf()))
    store_a_fea_result(s, build_into_the_set(s, brief_id))
    kept = await propose(s, brief_id, row(shelf()), deflection(hole_hook()))
    assert len(json.loads(json.dumps(kept["requirements"]))) == 2


async def test_a_brief_with_no_described_case_never_asks_for_a_result(s: Session) -> None:
    brief_id = await brief_of(s, row(hole_hook()))
    store_a_fea_result(s, build_into_the_set(s, brief_id))
    assert (await propose(s, brief_id, row(hole_hook()), deflection(hole_hook())))["proposal"] == 2


async def test_a_described_case_is_refused_for_a_brief_whose_reviewed_phrase_was_scored(
    s: Session,
) -> None:
    brief_id = await brief_of(s, row(hole_hook()))
    store_a_fea_result(s, build_into_the_set(s, brief_id))
    text = await refused(s, brief_id, row(shelf()))
    assert REFUSAL in text


async def test_the_person_declining_frees_the_proposal_to_leave_the_case_out(s: Session) -> None:
    brief_id = await brief_of(s, row(shelf()))
    store_a_fea_result(s, build_into_the_set(s, brief_id))
    s.person.answer = "decline"
    listed = await s.call("list_requirements", brief_id=brief_id)
    await s.call("ask_to_confirm", project_id=listed["project_id"])
    left_out = await propose(s, brief_id, row(hole_hook()))
    assert left_out["proposal"] == 2


async def test_a_declined_description_cannot_be_replaced_by_a_new_one_after_a_result(
    s: Session,
) -> None:
    brief_id = await brief_of(s, row(shelf()))
    store_a_fea_result(s, build_into_the_set(s, brief_id))
    s.person.answer = "decline"
    listed = await s.call("list_requirements", brief_id=brief_id)
    await s.call("ask_to_confirm", project_id=listed["project_id"])
    assert REFUSAL in await refused(s, brief_id, row(CLAMPED))
    assert (await propose(s, brief_id, row(heavier())))["proposal"] == 2


async def test_a_variant_of_another_brief_does_not_close_this_one(s: Session) -> None:
    other = await brief_of(s)
    store_a_fea_result(s, build_into_the_set(s, other, "# another brief's part\n"))
    brief_id = await brief_of(s, row(shelf()))
    assert (await propose(s, brief_id, row(CLAMPED)))["proposal"] == 2


async def test_a_described_case_is_never_an_assumption(s: Session) -> None:
    brief_id = await brief_of(s, row(hole_hook()))
    text = await s.text(
        "propose_requirements",
        brief_id=brief_id,
        assumptions=[
            {"target": {"kind": "min_safety_factor", "load": shelf(), "factor": 2}, "why": "w"}
        ],
    )
    assert "assumptions[0] is a described load case" in text
