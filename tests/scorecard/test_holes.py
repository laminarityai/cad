import re
from typing import Any

import pytest

from cad.checks.result import CheckResult, Comparator, Verdict
from cad.scorecard import holes, requirements
from cad.tables.fasteners import load_fasteners
from cad.tables.materials import UNITS
from tests.support.scorecard import checked, quantity, requirement, result, suite

M5_CLEARANCE: dict[str, Any] = {"kind": "fastener_holes", "size": "M5", "fit": "clearance"}
M4_TAPPED: dict[str, Any] = {"kind": "fastener_holes", "size": "M4", "fit": "tapped"}
M5_TAPPED: dict[str, Any] = {"kind": "fastener_holes", "size": "M5", "fit": "tapped"}
SHAFT: dict[str, Any] = {"kind": "plain_holes", "diameter": quantity(8, "mm")}


def counted(
    *diameters: float, verdict: Verdict = Verdict.PASS, open_ended: int = 0
) -> tuple[CheckResult, ...]:
    measured = {f"hole_diameter__{at}": (size, "mm") for at, size in enumerate(diameters)}
    return suite(
        result(
            "holes",
            verdict,
            hole_count=(len(diameters), "dimensionless"),
            unclassified_openings=(open_ended, "dimensionless"),
            **measured,
        )
    )


def verdict_of(target: dict[str, Any], results: tuple[CheckResult, ...], **more: Any) -> Verdict:
    return checked(requirements.judge(requirement({**target, **more}), results)).verdict


@pytest.mark.parametrize(
    ("target", "sizes", "verdict"),
    [
        (M5_CLEARANCE, (5.5, 5.5), Verdict.PASS),
        (M5_CLEARANCE, (5.3,), Verdict.PASS),
        (M5_CLEARANCE, (5.8,), Verdict.PASS),
        (M5_CLEARANCE, (5.299,), Verdict.FAIL),
        (M5_CLEARANCE, (5.801,), Verdict.FAIL),
        (M5_CLEARANCE, (4.2, 4.2), Verdict.FAIL),
        (M5_CLEARANCE, (), Verdict.FAIL),
        (M4_TAPPED, (5.5, 5.5), Verdict.FAIL),
        (M5_TAPPED, (4.2, 4.2), Verdict.PASS),
        (M5_TAPPED, (4.134,), Verdict.PASS),
        (M5_TAPPED, (4.334,), Verdict.PASS),
        (M5_TAPPED, (4.4,), Verdict.FAIL),
        (M5_TAPPED, (5.5,), Verdict.FAIL),
        (SHAFT, (8.0,), Verdict.PASS),
        (SHAFT, (8.05,), Verdict.PASS),
        (SHAFT, (8.2,), Verdict.FAIL),
        (SHAFT, (7.9,), Verdict.FAIL),
    ],
)
def test_a_hole_counts_when_its_diameter_is_in_the_band_of_the_confirmed_size(
    target: dict[str, Any], sizes: tuple[float, ...], verdict: Verdict
) -> None:
    assert verdict_of(target, counted(*sizes)) == verdict


@pytest.mark.parametrize(
    ("sizes", "count", "verdict"),
    [
        ((5.5, 5.5), 2, Verdict.PASS),
        ((5.5, 5.5, 8.0), 2, Verdict.PASS),
        ((5.5,), 2, Verdict.FAIL),
        ((5.5, 5.5, 5.5), 2, Verdict.FAIL),
        ((4.2, 4.2), 2, Verdict.FAIL),
        ((), 1, Verdict.FAIL),
    ],
)
def test_a_stated_count_must_equal_the_matching_holes(
    sizes: tuple[float, ...], count: int, verdict: Verdict
) -> None:
    assert verdict_of(M5_CLEARANCE, counted(*sizes), count=count) == verdict


def test_with_no_count_a_second_matching_hole_is_not_a_failure() -> None:
    assert verdict_of(M5_CLEARANCE, counted(5.5, 5.5, 5.5)) == Verdict.PASS


def test_an_unclassified_opening_leaves_the_requirement_unknown_not_passed() -> None:
    unmeasured = counted(5.5, 5.5, verdict=Verdict.UNKNOWN, open_ended=1)
    assert verdict_of(M5_CLEARANCE, unmeasured) == Verdict.UNKNOWN
    assert verdict_of(M5_CLEARANCE, unmeasured, count=2) == Verdict.UNKNOWN
    assert (
        verdict_of(M5_CLEARANCE, counted(verdict=Verdict.UNKNOWN, open_ended=1)) == Verdict.UNKNOWN
    )


def test_more_matching_holes_than_confirmed_fails_even_when_an_opening_is_unclassified() -> None:
    unmeasured = counted(5.5, 5.5, 5.5, verdict=Verdict.UNKNOWN, open_ended=1)
    assert verdict_of(M5_CLEARANCE, unmeasured, count=2) == Verdict.FAIL


def test_a_check_that_could_not_measure_leaves_the_requirement_unknown() -> None:
    assert verdict_of(M5_CLEARANCE, suite(result("holes", Verdict.UNKNOWN))) == Verdict.UNKNOWN


def test_the_card_carries_the_table_band_as_the_limits_it_compared() -> None:
    judged = checked(requirements.judge(requirement(M5_CLEARANCE), counted(5.5)))
    row = load_fasteners().get("M5").clearance
    assert [(c.measure, c.comparator, c.limit) for c in judged.comparisons] == [
        ("hole_diameter", Comparator.AT_LEAST, UNITS.Quantity(row.close_mm, "mm")),
        ("hole_diameter", Comparator.AT_MOST, UNITS.Quantity(row.coarse_mm, "mm")),
    ]
    assert judged.check_id == "holes"
    assert not judged.researched


def test_a_tapped_hole_is_held_to_the_minor_diameter_of_its_thread() -> None:
    judged = checked(requirements.judge(requirement(M5_TAPPED), counted(4.2)))
    row = load_fasteners().get("M5").tapped
    assert [c.limit for c in judged.comparisons] == [
        UNITS.Quantity(row.minor_min_mm, "mm"),
        UNITS.Quantity(row.minor_max_mm, "mm"),
    ]


def test_a_plain_hole_is_held_to_its_stated_diameter_within_the_tolerance() -> None:
    judged = checked(requirements.judge(requirement(SHAFT), counted(8.0)))
    assert [c.limit.m_as("mm") for c in judged.comparisons] == pytest.approx(  # pyright: ignore[reportUnknownMemberType]
        [8 - holes.PLAIN_TOLERANCE_MM, 8 + holes.PLAIN_TOLERANCE_MM]
    )


@pytest.mark.parametrize(
    ("target", "sizes", "count"),
    [
        (M5_CLEARANCE, (5.5, 5.5), None),
        (M5_CLEARANCE, (5.5,), 2),
        (M5_CLEARANCE, (5.5, 5.5, 5.5), 2),
        (M5_CLEARANCE, (), None),
        (M5_TAPPED, (4.2,), 1),
    ],
)
def test_a_reason_holds_no_digit(
    target: dict[str, Any], sizes: tuple[float, ...], count: int | None
) -> None:
    more: dict[str, Any] = {} if count is None else {"count": count}
    reason = checked(requirements.judge(requirement({**target, **more}), counted(*sizes))).reason
    assert re.search(r"\d", reason) is None


def test_an_unknown_result_carries_a_comparison_verdict_of_unknown() -> None:
    judged = checked(
        requirements.judge(requirement(M5_CLEARANCE), suite(result("holes", Verdict.UNKNOWN)))
    )
    assert {c.verdict for c in judged.comparisons} == {Verdict.UNKNOWN}
