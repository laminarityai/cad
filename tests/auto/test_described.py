"""Harness case 6, Auto: a pass on a described load case counts toward the stop, and the report
names it."""

from typing import Final

from cad.auto.model import AllPass, Revised, Standing, Started, Stopped
from cad.auto.step import fold, standing_of
from cad.checks.result import Verdict
from cad.conversations.model import ConversationId
from cad.scorecard.model import AgainstBrief, Checked, RequirementResult
from tests.support.scorecard import offline_card

START: Final = Started(
    conversation=ConversationId("c1"),
    brief_id="b" * 16,
    project="p-" + "0" * 16,
    decision_sha256="d" * 64,
    material_key="prusament-pla",
    watermark=(("b" * 16, 1),),
    conflicts=(),
)


def row(rid: str, verdict: Verdict, described: bool = False) -> Checked:
    return Checked(
        requirement_id=rid,
        statement=rid,
        check_id="fea",
        verdict=verdict,
        reason="",
        comparisons=(),
        load_case="described" if described else None,
    )


def standing(*rows: RequirementResult) -> Standing:
    basis = AgainstBrief(
        brief_id="b" * 16,
        decision_sha256="d" * 64,
        requirements=rows,
        unverified_requirements=(),
    )
    found = standing_of(offline_card(basis).model_copy(update={"results": ()}), 1, "c" * 64)
    assert isinstance(found, Standing)
    return found


def test_a_standing_names_the_rows_that_rest_on_a_described_load_case() -> None:
    found = standing(row("r1", Verdict.PASS), row("r2", Verdict.PASS, described=True))
    assert found.described == ("r2",)


def test_a_pass_on_a_described_load_case_stops_the_run_and_the_report_names_it() -> None:
    state = fold((START, Revised(standing=standing(row("r1", Verdict.PASS, described=True)))))
    assert isinstance(state, Stopped)
    assert state.reason == AllPass(researched=(), unverified=(), described=("r1",))
    assert "- requirement r1: passes, on a load case the agent described" in state.report
    assert (
        "These pass on a load case the agent described and the person confirmed: r1."
        in state.report
    )


def test_a_report_without_a_described_load_case_does_not_mention_one() -> None:
    state = fold((START, Revised(standing=standing(row("r1", Verdict.PASS)))))
    assert isinstance(state, Stopped)
    assert "described" not in state.report
    assert "described" not in state.reason.model_dump()


def test_a_fail_on_a_described_load_case_is_a_fail_the_run_revises_against() -> None:
    state = fold((START, Revised(standing=standing(row("r1", Verdict.FAIL, described=True)))))
    assert not isinstance(state, Stopped)
    assert state.failing == ("r1",)
