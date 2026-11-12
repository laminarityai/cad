import pytest
from tracking import (
    OTHER,
    By,
    Decided,
    Ratio,
    RequirementOutcome,
    describe,
    describe_apart,
    family,
    outcomes_of,
    track,
)

from cad.checks.result import ReadResearched, Verdict
from cad.scorecard.model import AgainstBrief, Checked, RequirementResult, Unverified
from cad.scorecard.waiting import Waiting
from tests.support.cards import genuine_card

RESEARCH = ReadResearched(field="density", url="https://example.com", quote="1.2", sha256="")


def outcome(verdict: Verdict, by: By, statement: str = "") -> RequirementOutcome:
    return RequirementOutcome("r", verdict, by, statement)


def checked(requirement_id: str, verdict: Verdict, *, researched: bool = False) -> Checked:
    return Checked(
        requirement_id=requirement_id,
        statement=f"statement of {requirement_id}",
        check_id="mass",
        verdict=verdict,
        reason="",
        comparisons=(),
        basis="researched" if researched else "checks",
        researched=(RESEARCH,) if researched else (),
    )


def judged(*requirements: RequirementResult) -> tuple[RequirementOutcome, ...]:
    unverified = tuple(one.requirement_id for one in requirements if isinstance(one, Unverified))
    basis = AgainstBrief(
        brief_id="b",
        decision_sha256="d" * 64,
        requirements=requirements,
        unverified_requirements=unverified,
    )
    return outcomes_of(genuine_card(basis=basis))


def test_only_a_pass_by_a_reviewed_check_counts_as_a_strict_pass() -> None:
    tracking = track(
        (
            outcome(Verdict.PASS, By.TEAM),
            outcome(Verdict.PASS, By.RESEARCHED),
            outcome(Verdict.UNKNOWN, By.WAITING),
            outcome(Verdict.FAIL, By.TEAM),
            outcome(Verdict.UNKNOWN, By.NONE),
        )
    )
    assert tracking.strict_pass_rate == Ratio(2, 5)
    assert tracking.reviewed_coverage == Ratio(3, 5)
    assert describe(tracking.strict_pass_rate) == "2/5 (40%)"


def test_a_researched_verdict_and_a_cited_one_each_land_on_their_own_line() -> None:
    tracking = track(
        judged(
            checked("cited", Verdict.PASS),
            checked("researched", Verdict.PASS, researched=True),
            Waiting(requirement_id="waiting", statement="Deflects at most 1 mm", check_id="fea"),
        )
    )
    assert tracking.reviewed_coverage == Ratio(2, 3)
    assert tracking.by == {
        By.TEAM: Decided(1, 1),
        By.RESEARCHED: Decided(1, 1),
        By.WAITING: Decided(1, 0),
        By.NONE: Decided(0, 0),
    }
    assert describe_apart(tracking)[:2] == [
        "requirements by a team check on reviewed table values: 1, 1 passing",
        "requirements by a team check on researched values: 1, 1 passing",
    ]


def test_requirements_no_check_decides_are_tallied_by_family() -> None:
    tracking = track(
        judged(
            checked("mass", Verdict.FAIL),
            Unverified(requirement_id="a", statement="Two holes that fit an M5 bolt"),
            Unverified(requirement_id="b", statement="Tapped for M4"),
            Unverified(requirement_id="c", statement="Walls at least 2 mm thick"),
            Unverified(requirement_id="d", statement="Looks friendly"),
        )
    )
    assert tracking.uncovered == {"holes and fasteners": 2, "walls and thickness": 1, OTHER: 1}
    assert describe_apart(tracking)[-1] == (
        "requirements no check decides, by keyword family: "
        "holes and fasteners 2, walls and thickness 1, other 1"
    )


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("Holds 5 kg hanging from the hook", "loads and stiffness"),
        ("Takes a 20 N push without breaking", "loads and stiffness"),
        ("Snaps onto a 35 mm DIN rail", "fits and clearances"),
        ("L bracket 1/4 in thick and 1.5 in wide", "walls and thickness"),
        ("Clamps a 31.8 mm handlebar", "fits and clearances"),
        ("Prints without supports", "printing and process"),
        ("A 120 mm long arm", "sizes and shapes"),
        ("Looks friendly", OTHER),
    ],
)
def test_the_first_family_whose_words_appear_wins(statement: str, expected: str) -> None:
    assert family(statement) == expected


def test_no_requirement_no_check_decides_reads_none() -> None:
    assert describe_apart(track(judged(checked("mass", Verdict.PASS))))[-1] == (
        "requirements no check decides, by keyword family: none"
    )
