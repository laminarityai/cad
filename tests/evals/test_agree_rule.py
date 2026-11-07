import pytest
from agree import (
    EXTENT_TOL_MM,
    UNSCORED,
    VOLUME_TOL_MM3,
    CardSide,
    Extents,
    GraderSide,
    agree_rule,
)

BOX: Extents = (6.0, 50.0, 100.0)


def card(
    closed_solid: str = "pass", volume: float | None = 29509.72, extents: Extents | None = BOX
) -> CardSide:
    return CardSide(closed_solid, volume, extents)


def grader(
    category: str = "pass", volume: float | None = 29509.72, extents: Extents | None = BOX
) -> GraderSide:
    return GraderSide(category, volume, extents)


def test_the_tolerances_are_the_ones_the_plan_fixed() -> None:
    assert (VOLUME_TOL_MM3, EXTENT_TOL_MM) == (0.01, 0.002)


def test_equal_valid_solids_agree() -> None:
    assert agree_rule(card(), grader()).agrees


def test_a_volume_off_by_0_02_mm3_disagrees() -> None:
    result = agree_rule(card(volume=29509.74), grader())
    assert not result.agrees
    assert "volume" in result.reasons[0]


def test_a_volume_off_by_0_005_mm3_agrees() -> None:
    assert agree_rule(card(volume=29509.725), grader()).agrees


@pytest.mark.parametrize("offset", [0.003, -0.003])
def test_an_extent_off_by_0_003_mm_disagrees(offset: float) -> None:
    result = agree_rule(card(extents=(6.0, 50.0 + offset, 100.0)), grader())
    assert not result.agrees
    assert "extents" in result.reasons[0]


def test_an_extent_off_by_0_001_mm_agrees() -> None:
    assert agree_rule(card(extents=(6.0, 50.001, 100.0)), grader()).agrees


def test_every_disagreement_is_reported_not_only_the_first() -> None:
    result = agree_rule(card(volume=1.0, extents=(1.0, 2.0, 3.0)), grader())
    assert len(result.reasons) == 2


@pytest.mark.parametrize("category", ["pass", "bbox", "volume", "features"])
def test_a_part_specific_failure_still_counts_as_a_valid_solid(category: str) -> None:
    assert agree_rule(card(), grader(category=category)).agrees


@pytest.mark.parametrize("category", ["no_output", "invalid_solid"])
def test_a_failed_closed_solid_agrees_with_an_invalid_grade_without_numbers(
    category: str,
) -> None:
    assert agree_rule(card("fail", None, None), grader(category, None, None)).agrees


@pytest.mark.parametrize("category", ["no_output", "invalid_solid"])
def test_a_passing_closed_solid_disagrees_with_an_invalid_grade(category: str) -> None:
    result = agree_rule(card(), grader(category, None, None))
    assert not result.agrees
    assert category in result.reasons[0]


@pytest.mark.parametrize("verdict", ["fail", "unknown"])
def test_a_closed_solid_that_does_not_pass_disagrees_with_a_valid_grade(verdict: str) -> None:
    assert not agree_rule(card(verdict, None, None), grader()).agrees


def test_a_variant_with_no_scorecard_never_agrees() -> None:
    result = agree_rule(CardSide(UNSCORED, None, None), grader("no_output", None, None))
    assert not result.agrees


def test_a_missing_number_on_either_side_disagrees_when_both_call_the_solid_valid() -> None:
    assert not agree_rule(card(volume=None), grader()).agrees
    assert not agree_rule(card(), grader(extents=None)).agrees
