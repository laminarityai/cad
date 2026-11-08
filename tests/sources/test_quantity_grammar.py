import pint
import pytest

from cad.sources.quantities import Reason, Refusal, one_quantity
from cad.tables.materials import magnitude


def kg_per_m3(quote: str) -> float:
    result = one_quantity(quote, "density")
    assert isinstance(result, pint.Quantity), result
    return magnitude(result, "kg/m^3")


def refusal(quote: str) -> Refusal:
    result = one_quantity(quote, "density")
    assert isinstance(result, Refusal), result
    return result


REFUSED_OUTSIDE_THE_GRAMMAR = [
    "Density 1.24 g/cm3, filled 1.36 g/cm3 \u00b1 0.02 g/cm3",
    "Density 1.36 g/cm3 \u00b1 0.02 g/cm3 (unfilled) 1.24",
    "Density 1.24 g/cm3; GF30 1.36 \u00b1 0.02 g/cm3",
    "Density 1.24 g/cm\u00b3 \u00b1 0.02 g/cm\u00b3 (unfilled), 1.36 g/cm3",
    "Density 7850 kg/m3 \u00b1 10 kg/m3 or 7.9 g/cm3",
    "Density 1 \u00b1 0.1 240 kg/m3",
    "Density 1.24 g/cm3 \u00b1 20 kg/m3",
    "Density (max): 1.30 g/cm3",
    "Density max.: 1.30 g/cm3",
    "Density max = 1.30 g/cm3",
    "Density \u2265 1.30 g/cm3",
    "Density \u2a7e 1.30 g/cm3",
    "Density \u2267 1.30 g/cm3",
    "Density \u2a7d 1.30 g/cm3",
    "Density < = 1.30 g/cm3",
    "Density >= 1.30 g/cm3",
    "Density <= 1.30 g/cm3",
    "Density &lt; 1.30 g/cm3",
    "Density &gt; 1.30 g/cm3",
    "Density up to 1.30 g/cm3",
    "Density less than 1.30 g/cm3",
    "Density more than 1.30 g/cm3",
    "Density 1.30 g/cm3 or less",
    "Density 1.20 g/cm3 or more",
    "Density min/max 1.20/1.30 g/cm3",
    "Density max - 1.30 g/cm3",
    "Density - max 1.30 g/cm3",
    "Density 1.30 g/cm3, max",
    "Density 1.30 g/cm3 (maximum)",
    "Density 1.30 g/cm3 max.",
    "Density 1.30 g/cm3 ; max",
    "Density min. 1.20 g/cm3",
    "Density 1.20 g/cm3 minimum",
    "Density < 1.30 [g/cm3]",
    "Density [g/cm3] < 1.30",
    "Density [g/cm3] max 1.30",
    "Part 3 400 kg/m3",
    "Density 1.24 g/cm3 1.24",
    "Density 1.240 kg/m3 1.24",
    "Density 1 240 kg/m3 240",
    "Density 1.24 g/cm3 (7.85 grams per cubic centimeter)",
    "Density 7.85 grams per cubic centimeter",
    "Density 1.24 g/cm3 (0.0448 pounds per cubic inch)",
    "Density 1.24 cm3/g",
    "Density 1.24 g/cm3/K",
    "Density 1.24 g/cm3 EN 1.36 g/cm3",
    "Density ISO 1240 kg/m3",
    "Density EN 1.24 g/cm3",
    "Density 8 t m - 3 samples",
    "Density 8 t m-3 samples",
    "Density 1.24 g/cm3 1.24 g/cm3",
    "Density \u03c1 1.19 1.19 1.19 g/cm\u00b3 ISO 1183",
    "Density 1.21 g/cm3 1.21 g/cm3 ASTM D792",
    "Density \u22481.24 g/cm3",
    "Density ~1.24 g/cm3",
    "Density 1.14 g/cm3, filled ~1.36 g/cm3",
    "Density approx. 1.24 g/cm3",
    "Density 1.24 g/cm3 (23 \u00b0C)",
    "Density 1.24 g/cm3 at room temperature",
    "Density of the part",
    "see the datasheet",
    "Density 1.24 g/cm3 and specific gravity 1.3",
    "Density 1.24 g/cm3 (\u00b12%)",
    "PA6 GF30 1.36 g/cm3",
    "Density 1.24 g/cm3 30% glass",
]


@pytest.mark.parametrize("quote", REFUSED_OUTSIDE_THE_GRAMMAR)
def test_refuses_every_quote_with_text_the_grammar_does_not_account_for(quote: str) -> None:
    assert isinstance(one_quantity(quote, "density"), Refusal), quote


def test_names_the_first_token_the_grammar_cannot_account_for() -> None:
    result = refusal("Density 1.24 g/cm3 and 1.36")
    assert result.reason is Reason.UNRECOGNISED_TEXT
    assert "'and'" in result.detail


@pytest.mark.parametrize(
    "quote",
    [
        "Part 3 400 kg/m3",
        "Density 1.24 g/cm3 1.24",
        "Density 1.24 g/cm3 \u22481.36",
    ],
)
def test_a_second_number_or_stray_word_is_unrecognised_text(quote: str) -> None:
    assert refusal(quote).reason is Reason.UNRECOGNISED_TEXT


@pytest.mark.parametrize(
    "quote",
    [
        "Density 1.24 g/cm3, filled 1.36 g/cm3 \u00b1 0.02 g/cm3",
        "Density 1.24 g/cm\u00b3 \u00b1 0.02 g/cm\u00b3 (unfilled), 1.36 g/cm3",
        "Density 7850 kg/m3 \u00b1 10 kg/m3 or 7.9 g/cm3",
        "Density 1.24 g/cm3 1.24 g/cm3",
    ],
)
def test_two_values_with_units_are_several_quantities(quote: str) -> None:
    assert refusal(quote).reason is Reason.SEVERAL_QUANTITIES


@pytest.mark.parametrize(
    "quote",
    [
        "Density (max): 1.30 g/cm3",
        "Density >= 1.30 g/cm3",
        "Density &lt; 1.30 g/cm3",
        "Density up to 1.30 g/cm3",
        "Density less than 1.30 g/cm3",
        "Density 1.30 g/cm3 or less",
        "Density \u2a7d 1.30 g/cm3",
        "Density min/max 1.20/1.30 g/cm3",
    ],
)
def test_every_bound_spelling_is_a_bound(quote: str) -> None:
    assert refusal(quote).reason is Reason.BOUND


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density 1.24 g/cm3 \u00b1 0.02", 1240.0),
        ("Density 1.24 \u00b1 0.02 g/cm3", 1240.0),
        ("Density 1.24 g/cm3 \u00b1 0.02 g/cm3", 1240.0),
        ("Density 1240 kg/m3 \u00b1 20 kg/m3", 1240.0),
        ("Typical density 1.24 g/cm3", 1240.0),
        ("Nominal Density: 1.24 g/cm3", 1240.0),
        ("Dichte 1,24 g/cm3", 1240.0),
        ("Densit\u00e9 1.24 g/cm3", 1240.0),
        ("Mass density = 1.24 g/cm3", 1240.0),
        ("DIN EN ISO 1183-1 Density 1.24 g/cm3", 1240.0),
        ("Density ISO 1183:2019 1.24 g/cm3", 1240.0),
        ("Density ASTM D792 1.24 g/cm3 at 23 \u00b0C, 50 % RH", 1240.0),
        ("Density 1.24 g/cm3 @ 23\u00b0C", 1240.0),
        ("Density 1.24 g/cm3 at 1 bar", 1240.0),
    ],
)
def test_reads_what_the_grammar_allows(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected, rel=1e-6)
