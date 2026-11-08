import time

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


NESTED_EXPONENTS = [
    "Density 1.24 g/cm^9",
    "Density 1.24 g/cm^99",
    "Density 1.24 g/cm^9^9",
    "Density 1.24 g/cm**9**9",
    "Density 1.24 g/cm**9**9**2",
    "Density 1.24 g/cm**9**9**9",
    "Density 1.24 g/cm^9^9^9",
    "Density 1.24 g/cm99999999999999999999",
    "Density 1.24 g/cm**99999999",
    "Density 1.24 g/cm^-9^9^9",
    "Density 1.24 kg/m^9^9^9",
    "1.24 g^9^9^9",
]


@pytest.mark.parametrize("quote", NESTED_EXPONENTS)
def test_a_nested_exponent_is_refused_within_100_ms(quote: str) -> None:
    started = time.perf_counter()
    result = refusal(quote)
    assert time.perf_counter() - started < 0.1
    assert result.reason is Reason.UNKNOWN_UNIT


@pytest.mark.parametrize(
    ("quote", "dimension"),
    [
        ("Density 1.24 MPa", "pressure"),
        ("Density 12 mm", "length"),
        ("Density 1.24 g", "mass"),
        ("Density 7850 kg/m", "mass per length"),
        ("Density 7850 kg/m2", "mass per area"),
        ("Density 0.098 lbs./in.", "mass per length"),
    ],
)
def test_names_the_dimension_of_a_known_wrong_unit(quote: str, dimension: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.WRONG_DIMENSION
    assert f"measures {dimension}," in result.detail


WIDE_TOLERANCES = [
    "Density 1.24 ± 1.36 g/cm3",
    "Density 1240 ± 7850 kg/m3",
    "Density 1 ± 1.24 g/cm3",
    "Density 1.24 ± 999 % g/cm3",
    "Density 1.24 ± 1.24 g/cm3",
    "Density 1.24 ± 2.48 g/cm3",
    "Density 7.85 ± 8 g/cm3",
    "Density 1240 ± 1000 kg/m3",
    "Density 1.24 ± 100 % g/cm3",
    "Density 1.24 g/cm3 ± 1.36 g/cm3",
    "Density g/cm3 1.24 ± 1.36",
    "Density [g/cm3] 1.24 ± 7.85",
    "Density 0.6 ± 0.95 g/cm3",
    "Density 1.0 ± 7.8 g/cm3",
    "Density 1.24 g/cm3 ± 11 %",
    "Density 1240 kg/m3 ± 125",
]


@pytest.mark.parametrize("quote", WIDE_TOLERANCES)
def test_refuses_a_tolerance_over_a_tenth_of_the_value(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.WIDE_TOLERANCE
    assert "10%" in result.detail


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density 1.24 ± 0.124 g/cm3", 1240.0),
        ("Density 1240 kg/m3 ± 124", 1240.0),
        ("Density 1.24 g/cm3 ± 10 %", 1240.0),
        ("Density 1.24 ± 0.02 g/cm3", 1240.0),
        ("Density g/cm3 1.24 ± 0.02", 1240.0),
        ("Density 1.24 g/cm3 ±2%", 1240.0),
    ],
)
def test_reads_a_tolerance_up_to_a_tenth_of_the_value(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected)


def test_refuses_a_tolerance_that_is_itself_ambiguous() -> None:
    assert refusal("Density 1240,5 ± 1,240 kg/m3").reason is Reason.AMBIGUOUS_NUMBER


AMBIGUOUS_SEPARATORS = [
    "Density 1.204 kg/m3 at 20 °C",
    "Dichte 1,225 kg/m³",
    "Density 1.225 kg/m3",
    "Density 16.000 kg/m3",
    "Density 2.500 kg/m3",
    "Density 1,240 kg/m3",
    "Density 7.850 kg/m3",
    "Density 8,030 kg/m3",
    "Density 1,240 g/cm3",
    "Density 1.240 kg/m3",
    "Density 2 450 kg/m3",
    "Density 4 450 kg/m3",
    "Density 5 120 kg/m3",
    "Density 1 240 kg/m3",
    "Density 1 240.0 kg/m3",
    "Density 0 950 kg/m3",
    "Density 000 950 kg/m3",
]


@pytest.mark.parametrize("quote", AMBIGUOUS_SEPARATORS)
def test_refuses_a_number_whose_separator_is_ambiguous(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert "fit the band" not in result.detail


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density 1,240.5 kg/m3", 1240.5),
        ("Density 1.240,5 kg/m3", 1240.5),
        ("Density 1.24 g/cm3", 1240.0),
        ("Density 7.85 g/cm3", 7850.0),
        ("Density 1,5 g/cm3", 1500.0),
        ("Density 0,915 g/cm3", 915.0),
        ("Density 1240.500 kg/m3", 1240.5),
        ("Density 1240 kg/m3", 1240.0),
    ],
)
def test_reads_a_number_whose_separator_is_unambiguous(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected)


def test_a_grouping_of_several_groups_is_one_number() -> None:
    assert refusal("Density 1.240.500 kg/m3").reason is Reason.OUT_OF_BAND


def test_the_band_rejects_a_reading_but_never_chooses_one() -> None:
    assert refusal("Density 0.016 g/cm3").reason is Reason.OUT_OF_BAND
    assert refusal("Dichte 1,2041 kg/m³").reason is Reason.OUT_OF_BAND


@pytest.mark.parametrize(
    "quote",
    [
        "Density DIN 1 2400 kg/m3",
        "Density GB/T 1 2400 kg/m3",
        "Density DIN 12 4000 kg/m3",
        "Density ASTM D7 9200 kg/m3",
        "Density DIN 7 8500 kg/m3",
        "Density ISO 1183-1 240 kg/m3",
        "Density ISO 1183 1240 kg/m3",
        "Density DIN 7 850,5 kg/m3",
    ],
)
def test_a_standard_followed_by_a_digit_group_is_refused(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert "standard" in result.detail


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density ISO 1183, 1240 kg/m3", 1240.0),
        ("Density (ASTM D792) 1240 kg/m3", 1240.0),
    ],
)
def test_a_standard_followed_by_punctuation_still_reads(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected)


@pytest.mark.parametrize(
    "quote",
    ["Density 1240 kg/m3 at 1 950 Pa", "Density 1 240 % RH 950 kg/m3"],
)
def test_a_condition_with_a_space_grouped_number_is_refused(quote: str) -> None:
    assert isinstance(one_quantity(quote, "density"), Refusal)


@pytest.mark.parametrize(
    "quote", ["Density at -40 °C 1.24 g/cm3", "Density at \u221240 °C 1.24 g/cm3"]
)
def test_a_negative_temperature_is_a_condition_not_a_negative_value(quote: str) -> None:
    assert kg_per_m3(quote) == pytest.approx(1240.0)


def test_a_space_grouped_number_says_it_could_be_one_or_several() -> None:
    result = refusal("Density 0 950 kg/m3")
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert "950 or 950" not in result.detail
    assert "one number or several" in result.detail


@pytest.mark.parametrize("quote", ["Density 1'240 kg/m3", "Density 1'240.5 kg/m3"])
def test_an_apostrophe_grouping_is_named(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.UNRECOGNISED_TEXT
    assert "apostrophe" in result.detail
    assert "no unit" not in result.detail


@pytest.mark.parametrize("quote", ["Density 1.24 \u0261/cm3", "Density 1.24 K\u0261/m3"])
def test_a_lookalike_unit_letter_is_an_unknown_unit(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.UNKNOWN_UNIT
    assert "\u0261" in result.detail
