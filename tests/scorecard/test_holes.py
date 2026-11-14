import re
from typing import Any

import pytest

from cad.checks.result import CheckResult, Comparator, Verdict
from cad.scorecard import requirements
from cad.tables.fasteners import load_fasteners
from cad.tables.materials import UNITS
from tests.support.scorecard import checked, quantity, requirement, result, suite

M5_CLEARANCE: dict[str, Any] = {"kind": "fastener_holes", "size": "M5", "fit": "clearance"}
M4_TAPPED: dict[str, Any] = {"kind": "fastener_holes", "size": "M4", "fit": "tapped"}
M5_TAPPED: dict[str, Any] = {"kind": "fastener_holes", "size": "M5", "fit": "tapped"}
SHAFT: dict[str, Any] = {"kind": "plain_holes", "diameter": quantity(8, "mm")}
SHAFT_H7: dict[str, Any] = {**SHAFT, "tolerance": {"kind": "class", "key": "H7"}}
SHAFT_WIDE: dict[str, Any] = {
    **SHAFT,
    "tolerance": {"kind": "plus_minus", "within": quantity(0.1, "mm")},
}
M5_CLOSE: dict[str, Any] = {**M5_CLEARANCE, "series": "close"}
M5_COARSE: dict[str, Any] = {**M5_CLEARANCE, "series": "coarse"}


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
        (SHAFT_H7, (8.0,), Verdict.PASS),
        (SHAFT_H7, (8.01,), Verdict.PASS),
        (SHAFT_H7, (8.015,), Verdict.PASS),
        (SHAFT_H7, (8.05,), Verdict.FAIL),
        (SHAFT_H7, (7.99,), Verdict.FAIL),
        (SHAFT_WIDE, (8.05,), Verdict.PASS),
        (SHAFT_WIDE, (8.1,), Verdict.PASS),
        (SHAFT_WIDE, (8.2,), Verdict.FAIL),
        (M5_CLOSE, (5.3,), Verdict.PASS),
        (M5_CLOSE, (5.5,), Verdict.FAIL),
        (M5_COARSE, (5.8,), Verdict.PASS),
        (M5_COARSE, (5.3,), Verdict.FAIL),
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


@pytest.mark.parametrize(
    ("verdict", "whole", "plate", "judged"),
    [(Verdict.UNKNOWN, 1, 0, Verdict.PASS), (Verdict.PASS, 0, 1, Verdict.UNKNOWN)],
    ids=["another body's opening", "an opening another body's hole explains"],
)
def test_a_requirement_on_a_body_waits_only_for_that_body_s_own_openings(
    verdict: Verdict, whole: int, plate: int, judged: Verdict
) -> None:
    holes = result(
        "holes",
        verdict,
        hole_count=(1, "dimensionless"),
        hole_diameter__0=(5.5, "mm"),
        unclassified_openings=(whole, "dimensionless"),
        hole_count__plate=(1, "dimensionless"),
        hole_diameter__plate__0=(5.5, "mm"),
        unclassified_openings__plate=(plate, "dimensionless"),
    )
    assert verdict_of(M5_CLEARANCE, suite(holes), body="plate") == judged


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


@pytest.mark.parametrize(
    ("target", "url"),
    [
        (M5_CLEARANCE, "https://de.wikipedia.org/wiki/Durchgangsloch"),
        (M5_TAPPED, "https://amesweb.info/Screws/metric-tap-drill-chart.aspx"),
        (SHAFT_H7, "https://en.wikipedia.org/wiki/IT_Grade"),
    ],
)
def test_the_card_cites_the_table_row_its_band_was_read_from(
    target: dict[str, Any], url: str
) -> None:
    card = checked(requirements.judge(requirement(target), counted(5.5))).model_dump(mode="json")
    [source] = card["sources"]
    assert source["url"] == url
    assert source["quote"]


def test_a_general_tolerance_cites_the_size_range_that_picked_its_row_and_the_limit() -> None:
    general = {**SHAFT, "tolerance": {"kind": "class", "key": "ISO 2768-m"}}
    card = checked(requirements.judge(requirement(general), counted(8.0))).model_dump(mode="json")
    assert [one["quote"] for one in card["sources"]] == [
        "0.5 Note 1 up to 3 over 3 up to 6 over 6 up to 30 over 30 up to 120 over 120 up to 400",
        "m ±0.1 ±0.1 ±0.2 ±0.3 ±0.5",
    ]


def test_a_band_the_person_stated_cites_no_table() -> None:
    card = checked(requirements.judge(requirement(SHAFT_WIDE), counted(8.0)))
    assert "sources" not in card.model_dump(mode="json")


def test_a_tapped_hole_is_held_to_the_minor_diameter_of_its_thread() -> None:
    judged = checked(requirements.judge(requirement(M5_TAPPED), counted(4.2)))
    row = load_fasteners().get("M5").tapped
    assert [c.limit for c in judged.comparisons] == [
        UNITS.Quantity(row.minor_min_mm, "mm"),
        UNITS.Quantity(row.minor_max_mm, "mm"),
    ]


def bounds(target: dict[str, Any]) -> list[float]:
    judged = checked(requirements.judge(requirement(target), counted(8.0)))
    return [c.limit.m_as("mm") for c in judged.comparisons]  # pyright: ignore[reportUnknownMemberType]


def test_a_plain_hole_with_no_tolerance_stored_is_held_to_0_05_mm() -> None:
    assert "tolerance" not in SHAFT
    assert bounds(SHAFT) == pytest.approx([7.95, 8.05])


def test_a_plain_hole_with_a_class_is_held_to_the_band_of_the_table() -> None:
    assert bounds(SHAFT_H7) == pytest.approx([8.0, 8.015])
    assert bounds({**SHAFT, "tolerance": {"kind": "class", "key": "ISO 2768-m"}}) == pytest.approx(
        [7.8, 8.2]
    )


def test_a_plain_hole_with_a_stated_length_is_held_to_it() -> None:
    assert bounds(SHAFT_WIDE) == pytest.approx([7.9, 8.1])


def test_a_clearance_series_is_held_to_its_one_diameter() -> None:
    row = load_fasteners().get("M5").clearance
    assert bounds(M5_CLOSE) == pytest.approx([row.close_mm, row.close_mm])
    assert bounds(M5_COARSE) == pytest.approx([row.coarse_mm, row.coarse_mm])


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


def marks(target: dict[str, Any], *sizes: float, count: int | None = None) -> list[Verdict]:
    more: dict[str, Any] = {} if count is None else {"count": count}
    judged = checked(requirements.judge(requirement({**target, **more}), counted(*sizes)))
    return [c.verdict for c in judged.comparisons]


def test_each_bound_is_marked_by_whether_enough_holes_meet_it() -> None:
    assert marks(M5_CLEARANCE, 4.2, 4.2, count=2) == [Verdict.FAIL, Verdict.PASS]
    assert marks(M5_CLEARANCE, 7.0, 7.0, count=2) == [Verdict.PASS, Verdict.FAIL]
    assert marks(M5_CLEARANCE, 5.5, 4.2, count=2) == [Verdict.FAIL, Verdict.PASS]
    assert marks(M5_CLEARANCE, 5.5, 5.5, count=2) == [Verdict.PASS, Verdict.PASS]
    assert marks(M5_CLEARANCE, 4.2) == [Verdict.FAIL, Verdict.PASS]
    assert marks(M5_CLEARANCE) == [Verdict.FAIL, Verdict.FAIL]


def test_marking_each_bound_leaves_the_requirement_verdict_as_the_count_decides() -> None:
    assert verdict_of(M5_CLEARANCE, counted(4.2, 7.0), count=1) == Verdict.FAIL
    assert marks(M5_CLEARANCE, 4.2, 7.0, count=1) == [Verdict.PASS, Verdict.PASS]
    assert verdict_of(M5_CLEARANCE, counted(5.5, 5.5, 5.5), count=2) == Verdict.FAIL
