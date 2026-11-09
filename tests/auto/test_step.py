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
    Unsettled,
)
from cad.auto.step import fold, standing_of
from cad.checks.result import ReadResearched, StepMissing, Verdict
from cad.scorecard.model import (
    AgainstBrief,
    AgentMeasurement,
    Checked,
    PendingCheck,
    RequirementResult,
    Scorecard,
    Unverified,
)
from cad.scorecard.requirements import UNCONFIRMED_PART
from cad.scorecard.waiting import Waiting

START: Final = Started(
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
    *rows: RequirementResult, pending: bool = False, agent: tuple[AgentMeasurement, ...] = ()
) -> Scorecard:
    results = (
        (PendingCheck(check_id="fea", formula="", sources=(), version="1"),) if pending else ()
    )
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
            r.requirement_id for r in rows if isinstance(r, Checked) and r.verdict is not PASS
        )
    else:
        assert isinstance(state, Stopped)
        assert state.reason == reason


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


def test_the_report_labels_research_and_lists_the_unverified() -> None:
    rows = (checked("r1", PASS, researched=True), unverified("r2"))
    state = run(Revised(standing=settle(card(*rows))))
    assert isinstance(state, Stopped)
    assert "- requirement r1: passes on researched data" in state.report
    assert "neither pass nor fail: r2" in state.report
    assert "Revisions tried: 1" in state.report


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
