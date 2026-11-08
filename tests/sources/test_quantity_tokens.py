import subprocess
import sys

import pytest

from cad.sources.quantities import Quantity, Reason, Refusal, one_quantity


def kg_per_m3(quote: str) -> float:
    result = one_quantity(quote, "density")
    assert isinstance(result, Quantity), result
    return result.canonical


def refusal(quote: str) -> Refusal:
    result = one_quantity(quote, "density")
    assert isinstance(result, Refusal), result
    return result


GLUED_SEPARATORS = [
    ",9 g/cm3",
    "Density ,9 g/cm3",
    "Dichte ,9 g/cm3",
    "Density ,5 g/cm3",
    "Density ,62 lb/ft3",
    "Density ,915 kg/m3",
    "Density (,9 g/cm3)",
    "Density:,9 g/cm3",
    "Density=,9 g/cm3",
    "Density ;9 g/cm3",
    "Density\n,9 g/cm3",
    "Density ﹐9 g/cm3",
    "Density ，9 g/cm3",
    "Density 9, g/cm3",
    "Density 1240, kg/m3",
    "Density 1;24 g/cm3",
    "Density 1:24 g/cm3",
    "Density (2400 kg/m3)",
    "Density ISO 1183,1240 kg/m3",
    "Density ISO 1183:1 1.24 g/cm3",
    "Density:1.24g/cm3",
]


@pytest.mark.parametrize("quote", GLUED_SEPARATORS)
def test_a_separator_that_touches_a_digit_is_ambiguous(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert "touches" in result.detail


STANDARD_THEN_NUMBER = [
    "Density DIN 1 2400.5 kg/m3",
    "Density DIN 1 2400,5 kg/m3",
    "Density DIN 1 2400.0 kg/m3",
    "Density ASTM D7 9200.0 kg/m3",
    "Density DIN 1 12.4 g/cm3",
    "Density DIN 1 2.4 g/cm3",
    "Density DIN 12 4.00 g/cm3",
    "Density ISO 1183 1240.5 kg/m3",
    "Density DIN 1 1240,5 kg/m3",
    "Density ISO 1183 12.4 g/cm3",
    "Density ISO 1183 1.24 g/cm³",
    "Density ASTM D792 1240 kg/m3",
    "Density ISO1183, GB/T1033 1.04 g/cm3 at 23°C",
    "Density DIN 1 (2400 kg/m3)",
]


@pytest.mark.parametrize("quote", STANDARD_THEN_NUMBER)
def test_a_standard_followed_by_any_number_is_ambiguous(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert "standard" in result.detail or "touches" in result.detail


WHITESPACE = [" ", "\t", "\n", "\x0b", "\x0c", "\r", "\x1c", "\x1f", "\x85", "\xa0", " "]
WHITESPACE += [" ", " ", " ", " ", " ", " ", "　"]


@pytest.mark.parametrize("space", WHITESPACE)
def test_every_whitespace_character_is_the_same_whitespace(space: str) -> None:
    assert kg_per_m3(f"Density{space}1.24{space}g/cm3") == pytest.approx(1240.0)
    assert refusal(f"Density DIN 1{space}2400 kg/m3").reason is Reason.AMBIGUOUS_NUMBER
    assert refusal(f"Density ISO 1183{space}1240 kg/m3").reason is Reason.AMBIGUOUS_NUMBER
    assert refusal(f"Density 1{space}240 kg/m3").reason is Reason.AMBIGUOUS_NUMBER


@pytest.mark.parametrize("quote", ["Density ASTM D792-1.24 g/cm3", "Density ISO 1183-1240 kg/m3"])
def test_a_standard_that_runs_into_a_number_is_ambiguous(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert "standard" in result.detail


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density [g/cm3] 1.24 ISO 1183", 1240.0),
        ("Density ISO 1183-1 g/cm³ 1.41", 1410.0),
        ("Density ISO 1183 g/cm³ 1.2", 1200.0),
        ("DIN EN ISO 1183-1 Density 1.24 g/cm3", 1240.0),
        ("Density ISO 1183, 1240 kg/m3", 1240.0),
        ("Density (ASTM D792) 1240 kg/m3", 1240.0),
        ("Density value: 1.24 g/cm3; ISO 1183", 1240.0),
        ("Density DIN 53479: 0,915 g/cm3", 915.0),
    ],
)
def test_a_standard_followed_by_a_separator_label_unit_or_the_end_still_reads(
    quote: str, expected: float
) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected)


@pytest.mark.parametrize(
    "quote",
    ["Density 01,240 g/cm3", "Density 001,240 g/cm3", "Density 00,915 g/cm3", "Density 0950 kg/m3"],
)
def test_a_whole_part_with_a_leading_zero_is_ambiguous(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert "leading zero" in result.detail


@pytest.mark.parametrize(
    ("quote", "expected"),
    [("Density 0,915 g/cm3", 915.0), ("Density 1240.500 kg/m3", 1240.5)],
)
def test_a_number_with_one_reading_still_reads(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected)


@pytest.mark.parametrize(
    "quote",
    [
        "Density 1.20/1.25 g/cm3",
        "Density 1.20 / 1.25 g/cm3",
        "Density 1.20...1.25 g/cm3",
        "Density 1.20…1.25 g/cm3",
        "Density 1.20-1.25g/cm3",
        "Density 1.20‐1.25 g/cm3",
        "Density 1.20‒1.25 g/cm3",
        "Density 1.20 bis 1.25 g/cm3",
    ],
)
def test_a_range_or_list_is_called_a_range(quote: str) -> None:
    assert refusal(quote).reason is Reason.RANGE


@pytest.mark.parametrize("quote", ["Density 1240. kg/m3", "Density 9. g/cm3"])
def test_a_trailing_decimal_point_is_named(quote: str) -> None:
    assert refusal(quote).reason is Reason.TRAILING_DECIMAL


@pytest.mark.parametrize("quote", ["Density 1·24 g/cm3", "Density 1·10 g/cm3"])
def test_a_middle_dot_between_digits_is_named(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.UNRECOGNISED_TEXT
    assert "U+00B7" in result.detail


@pytest.mark.parametrize(
    "quote",
    ["Density 1​240 kg/m3", "Density 1.2​4 g/cm3", "Density 1240 kg/m3﻿"],
)
def test_an_invisible_character_is_named_not_skipped(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.UNRECOGNISED_TEXT
    assert "U+" in result.detail


@pytest.mark.parametrize("quote", ["Density 1.24 g/cm 3", "Density 1240 kg/m 3"])
def test_a_detached_exponent_is_named(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.UNKNOWN_UNIT
    assert "exponent" in result.detail


def test_mg_is_read_as_milligrams() -> None:
    result = refusal("Density 1240 mg/cm3")
    assert result.reason is Reason.UNKNOWN_UNIT
    assert "milligram" in result.detail
    assert "megagram" not in result.detail


def test_a_percent_tolerance_is_compared_with_ten_percent() -> None:
    result = refusal("Density 1.24 ± 100 % g/cm3")
    assert result.reason is Reason.WIDE_TOLERANCE
    assert "of 1.24" not in result.detail
    assert "10%" in result.detail


def test_the_scorer_and_the_checks_never_load_the_reader() -> None:
    code = (
        "import sys, cad.scorecard.score, cad.checks.container.runner; "
        "print([n for n in sys.modules if n.startswith('cad.sources')])"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"
