from typing import Final

import pytest

from cad.auto.model import (
    AccountLimit,
    AllPass,
    Asked,
    Bounds,
    Capped,
    Event,
    Mark,
    NeedsPerson,
    Proposed,
    Revised,
    Running,
    Standing,
    Started,
    Stopped,
    StopReason,
    Tried,
    Unsettled,
)
from cad.auto.step import fold, report, standing_of
from cad.briefs.assumptions import Assumption
from cad.checks.container.fea import STIFFER
from cad.checks.result import CheckResult, ReadResearched, StepMissing, Verdict
from cad.conversations.model import ConversationId
from cad.scorecard import assumed
from cad.scorecard.material import MaterialUse, ReportedScorecard, SetByAgent
from cad.scorecard.model import (
    AgainstBrief,
    AgentChecked,
    AgentMeasurement,
    Checked,
    PendingCheck,
    RequirementResult,
    Scorecard,
    Unverified,
)
from cad.scorecard.requirements import UNCONFIRMED_PART
from cad.scorecard.waiting import Waiting
from tests.support.scorecard import TARGET, agent_checked, result

START: Final = Started(
    conversation=ConversationId("c1"),
    brief_id="b" * 16,
    project="p-" + "0" * 16,
    decision_sha256="d" * 64,
    material_key="prusament-pla",
    watermark=(("b" * 16, 1),),
    conflicts=(),
)
RESEARCH: Final = ReadResearched(field="density", url="https://example.com", quote="1.2", sha256="")


def checked(rid: str, verdict: Verdict, reason: str = "", researched: bool = False) -> Checked:
    return Checked(
        requirement_id=rid,
        statement=rid,
        check_id="mass",
        verdict=verdict,
        reason=reason,
        comparisons=(),
        basis="researched" if researched else "checks",
        researched=(RESEARCH,) if researched else (),
    )


def unverified(rid: str) -> Unverified:
    return Unverified(requirement_id=rid, statement=rid)


def card(
    *rows: RequirementResult,
    pending: bool = False,
    agent: tuple[AgentMeasurement, ...] = (),
    finished: tuple[CheckResult, ...] = (),
) -> Scorecard:
    results = (
        (PendingCheck(check_id="fea", formula="", sources=(), version="1"),) if pending else ()
    ) + finished
    return Scorecard(
        variant_id="v" * 16,
        material_key="prusament-pla",
        table_version="t",
        check_image_digest="i",
        brep_sha256="s",
        step=StepMissing(reason="none"),
        results=results,
        pending=("fea",) if pending else (),
        basis=AgainstBrief(
            brief_id="b" * 16,
            decision_sha256="d" * 64,
            requirements=rows,
            unverified_requirements=tuple(
                r.requirement_id for r in rows if isinstance(r, Unverified)
            ),
            agent_checked_requirements=tuple(
                r.requirement_id for r in rows if isinstance(r, AgentChecked)
            ),
        ),
        not_verified=agent,
    )


def settle(scored: Scorecard) -> Standing:
    standing = standing_of(scored, 1, "c" * 64)
    assert isinstance(standing, Standing)
    return standing


def run(*events: Event) -> Running | Stopped:
    return fold((START, *events))


PASS, FAIL, UNKNOWN = Verdict.PASS, Verdict.FAIL, Verdict.UNKNOWN


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ((checked("r1", PASS), checked("r2", PASS)), AllPass(researched=(), unverified=())),
        (
            (checked("r1", PASS), checked("r2", PASS, researched=True)),
            AllPass(researched=("r2",), unverified=()),
        ),
        ((checked("r1", PASS), unverified("r2")), AllPass(researched=(), unverified=("r2",))),
        (
            (checked("r1", PASS), agent_checked("r2", PASS), unverified("r3")),
            AllPass(researched=(), unverified=("r3",), agent_checked=("r2",)),
        ),
        ((checked("r1", PASS), agent_checked("r2", FAIL)), None),
        ((checked("r1", PASS), agent_checked("r2", UNKNOWN)), None),
        ((checked("r1", PASS), checked("r2", FAIL)), None),
        ((checked("r1", PASS), checked("r2", UNKNOWN, "no measure")), None),
        ((unverified("r1"), checked("r2", FAIL)), None),
        (
            (checked("r1", PASS), checked("r2", UNKNOWN, UNCONFIRMED_PART)),
            NeedsPerson(why="source_to_confirm", requirements=("r2",)),
        ),
    ],
)
def test_a_settled_revision_stops_the_run_only_by_the_table(
    rows: tuple[RequirementResult, ...], reason: StopReason | None
) -> None:
    state = run(Revised(standing=settle(card(*rows))))
    if reason is None:
        assert isinstance(state, Running)
        assert state.failing == tuple(
            r.requirement_id
            for r in rows
            if isinstance(r, Checked | AgentChecked) and r.verdict is not PASS
        )
    else:
        assert isinstance(state, Stopped)
        assert state.reason == reason


def test_a_revision_carries_the_check_reason_of_each_requirement_it_did_not_pass() -> None:
    bent = result("mass", UNKNOWN).model_copy(update={"reason": f"bends too far; {STIFFER}"})
    rows = (checked("r1", PASS), checked("r2", UNKNOWN, "no measure"), agent_checked("r3", FAIL))
    standing = settle(card(*rows, finished=(bent,)))
    assert standing.reasons == (("r2", f"bends too far; {STIFFER}"), ("r3", rows[2].reason))


def test_a_requirement_that_misses_a_limit_its_check_measured_carries_the_card_reason() -> None:
    measured = result("mass", PASS)
    standing = settle(card(checked("r1", FAIL, "misses"), finished=(measured,)))
    assert standing.reasons == (("r1", "misses"),)


@pytest.mark.parametrize(
    "scored",
    [
        card(checked("r1", PASS), pending=True),
        card(checked("r1", PASS), Waiting(requirement_id="r2", statement="", check_id="fea")),
    ],
)
def test_a_card_with_anything_pending_has_no_standing(scored: Scorecard) -> None:
    assert standing_of(scored, 1, "c" * 64) == Unsettled()


def test_a_failed_build_never_passes_even_with_no_requirement_to_fail() -> None:
    failed = Standing(revision=1, variant_id="v" * 16, code_sha256="c", built=False, marks=())
    state = run(Revised(standing=failed))
    assert isinstance(state, Running)
    assert state.history == (failed,)


def test_every_build_under_the_run_counts_once_and_none_stops_it() -> None:
    failed = Standing(revision=1, variant_id="v" * 16, code_sha256="b", built=False, marks=())
    state = run(
        Tried(code_sha256="a", variant_id="u" * 16),
        Tried(code_sha256="a", variant_id="u" * 16),
        Revised(standing=failed),
        Tried(code_sha256="b", variant_id="v" * 16),
    )
    assert isinstance(state, Running)
    assert (state.builds, state.history) == (("a", "b"), (failed,))
    text = report(state.history, len(state.builds), NeedsPerson(why="agent_asked", note="x"), {})
    assert "Builds tried: 2.\nThe latest the run checked did not build." in text
    assert failed.variant_id not in text


def test_the_report_labels_research_and_lists_the_unverified() -> None:
    rows = (checked("r1", PASS, researched=True), unverified("r2"))
    state = run(Revised(standing=settle(card(*rows))))
    assert isinstance(state, Stopped)
    assert "- requirement r1: passes on researched data" in state.report
    assert "neither pass nor fail: r2" in state.report
    assert "Builds tried: 1." in state.report


def test_the_report_lists_an_agent_check_pass_apart_with_its_label() -> None:
    rows = (checked("r1", PASS), agent_checked("r2", PASS))
    state = run(Revised(standing=settle(card(*rows))))
    assert isinstance(state, Stopped)
    assert "- requirement r2: passes the agent-written check you approved" in state.report
    assert "These pass an agent-written check you approved, not reviewed by our team: r2." in (
        state.report
    )
    assert "r1" not in state.reason.model_dump()["agent_checked"]


def test_the_persons_report_names_each_requirement_by_its_statement() -> None:
    rows = (checked("r1", PASS, researched=True), unverified("r2"))
    state = run(Revised(standing=settle(card(*rows))))
    assert isinstance(state, Stopped)
    said = {"r1": "Mass at most 150 g", "r2": "Holds 5 kg"}
    text = report(state.history, len(state.builds), state.reason, said)
    assert "- Mass at most 150 g: passes on researched data" in text
    assert "neither pass nor fail: Holds 5 kg" in text
    assert "r1" not in text


def test_the_persons_report_carries_each_checks_reason_and_names_the_option() -> None:
    rows = (checked("r1", UNKNOWN, "the mesh did not converge"), checked("r2", FAIL, "160 g"))
    standing = settle(card(*rows))
    said = {"r1": "Holds 5 kg", "r2": "Mass at most 150 g"}
    reason = NeedsPerson(why="agent_asked", note="stuck")
    text = report((standing,), 3, reason, said, "Thick walls, revision 2")
    assert "- Holds 5 kg: unknown, and it is not a pass: the mesh did not converge" in text
    assert "- Mass at most 150 g: fails: 160 g" in text
    assert "Builds tried: 3.\nThe latest the run checked is Thick walls, revision 2." in text
    assert "could not decide" not in text
    assert standing.variant_id not in text


@pytest.mark.parametrize(
    ("event", "reason"),
    [
        (
            Proposed(requirements=("r9",)),
            NeedsPerson(why="proposes_requirements", requirements=("r9",)),
        ),
        (
            Asked(note="I tried four walls"),
            NeedsPerson(why="agent_asked", note="I tried four walls"),
        ),
        (
            Capped(refused="v" * 16, reason="daily limit"),
            AccountLimit(refused="v" * 16, reason="daily limit"),
        ),
    ],
)
def test_each_stop_event_stops_the_run(event: Event, reason: StopReason) -> None:
    state = run(event)
    assert isinstance(state, Stopped)
    assert state.reason == reason


def test_the_agents_note_is_in_the_report_verbatim() -> None:
    state = run(Asked(note="Relax r1 or r2? Both cannot hold."))
    assert isinstance(state, Stopped)
    assert "Relax r1 or r2? Both cannot hold." in state.report


def test_a_stopped_run_absorbs_every_later_event() -> None:
    passing = Revised(standing=settle(card(checked("r1", PASS))))
    state = run(Asked(note="stuck"), passing, Capped(refused=None, reason="x"))
    assert isinstance(state, Stopped)
    assert state.reason == NeedsPerson(why="agent_asked", note="stuck")
    assert state.history == ()


def test_a_start_with_conflicts_is_stopped_before_any_revision() -> None:
    bounds = Bounds(
        quantity="mass", statement="min_mass 50 g > max_mass 40 g", requirements=("r1", "r2")
    )
    state = fold((START.model_copy(update={"conflicts": (bounds,)}),))
    assert isinstance(state, Stopped)
    assert state.reason == NeedsPerson(why="conflict", requirements=("r1", "r2"), bounds=(bounds,))
    assert "min_mass 50 g > max_mass 40 g" in state.report


@pytest.mark.parametrize("verdict", [PASS, FAIL, UNKNOWN])
def test_an_agent_measurement_cannot_change_the_run(verdict: Verdict) -> None:
    rows = (checked("r1", verdict), unverified("r2"))
    measured = AgentMeasurement(
        requirement_id="r2", title="it holds", code_sha256="0", code="", values=(), failed=None
    )
    plain = settle(card(*rows))
    with_agent = settle(card(*rows, agent=(measured,)))
    assert with_agent == plain
    assert run(Revised(standing=with_agent)) == run(Revised(standing=plain))
    assert dict(plain.marks)["r2"] is Mark.UNVERIFIED


def test_an_assumption_on_the_card_changes_no_standing() -> None:
    plain = card(checked("r1", PASS), unverified("r2"))
    held = ReportedScorecard(
        **dict(plain),
        material=MaterialUse(key="prusament-pla", set_by=SetByAgent()),
        assumptions=assumed.rows(
            [
                Assumption(
                    target=TARGET.validate_python(
                        {"kind": "max_mass", "mass": {"magnitude": 1, "unit": "g"}}
                    ),
                    why="x",
                )
            ],
            (),
        ),
    )
    assert held.assumptions
    assert standing_of(held, 1, "c" * 64) == standing_of(plain, 1, "c" * 64)
