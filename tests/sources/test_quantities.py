import time
from pathlib import Path

import pint
import pytest

from cad.sources.quantities import Reason, Refusal, one_quantity
from cad.tables.materials import Cited, load_materials, magnitude

SRC = Path(__file__).resolve().parents[2] / "src" / "cad"


def kg_per_m3(quote: str) -> float:
    result = one_quantity(quote, "density")
    assert isinstance(result, pint.Quantity), result
    return magnitude(result, "kg/m^3")


def refusal(quote: str) -> Refusal:
    result = one_quantity(quote, "density")
    assert isinstance(result, Refusal), result
    return result


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density 1.24 g/cm3", 1240.0),
        ("Density 1.24 g/cm³", 1240.0),
        ("Density 1.24 g/cc", 1240.0),
        ("Density 7850 kg/m3", 7850.0),
        ("Density 7850 kg/m^3", 7850.0),
        ("Density 7850 kg/m³", 7850.0),
        ("Density 0.29 lb/in3", 8027.8),
        ("Density 0.29 lb/in³", 8027.8),
        ("Density 0.29 lbs./in.3", 8027.8),
        ("Density 2.70 Mg/m3", 2700.0),
        ("Density 1,24 g/cm³", 1240.0),
        ("Density 8,030 kg/m3", 8030.0),
        ("Density 1 240 kg/m3", 1240.0),
        ("Density 1,240 g/cm3", 1240.0),
        ("Density 1.240 kg/m3", 1240.0),
        ("Density 1,240 kg/m3", 1240.0),
        ("Density 0,915 g/cm3", 915.0),
        ("Density 1.234,5 kg/m3", 1234.5),
        ("Density 1,234.5 kg/m3", 1234.5),
        ("Density 1.24 ± 0.02 g/cm³", 1240.0),
        ("Density [g/cm3] 1.24 ISO 1183", 1240.0),
        ("Density ISO1183, GB/T1033 1.04 g/cm3 at 23°C", 1040.0),
        ("Density ISO 1183 1.24 g/cm³", 1240.0),
        ("Density 7.87 g/cm3 at 20°C", 7870.0),
        ("Density g/cm3 8.5", 8500.0),
        ("Density ISO 1183-1 g/cm³ 1.41", 1410.0),
    ],
)
def test_reads_the_one_quantity(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected, rel=2e-3)


def test_keeps_the_unit_written_in_the_quote() -> None:
    result = one_quantity("Density 0.29 lb/in³", "density")
    assert isinstance(result, pint.Quantity)
    assert f"{result.units}" == "pound / inch ** 3"


@pytest.mark.parametrize("quote", ["", "   ", "Density"])
def test_refuses_a_quote_with_no_quantity(quote: str) -> None:
    assert refusal(quote).reason is Reason.NO_QUANTITY


@pytest.mark.parametrize(
    "quote",
    [
        "Density 1.24 g/cm³ or 7850 kg/m3",
        "Density 1.24 g/cm³ (0.0448 lb/in³)",
        "Nominal Density (68 °F/20 °C) 0.101 lbs./in.3 2.80 Mg/m3",
        "Density 1.21 g/cm3 (0.0437 lb/in3) 1.21 g/cm3 (0.0437 lb/in3) ASTM D792",
    ],
)
def test_refuses_two_or_more_quantities(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.SEVERAL_QUANTITIES
    assert "one" in result.needed


@pytest.mark.parametrize(
    "quote",
    [
        "Density 1.20-1.25 g/cm³",
        "Density 1.20 - 1.25 g/cm³",
        "Density 1.20 \u2013 1.25 g/cm³",
        "Density 1.20 to 1.25 g/cm³",
        "Density 1.20 g/cm³ - 1.25 g/cm³",
        "Density 1,20-1,25 g/cm³",
    ],
)
def test_refuses_a_range(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.RANGE
    assert "one value" in result.needed


@pytest.mark.parametrize(
    "quote",
    [
        "specific gravity 1.24",
        "Density 1.24",
        "Density 1.24 ISO 1183",
        "Density, lbs/in.3 (g/cm3) 0.29 (8.03)",
    ],
)
def test_refuses_a_number_with_no_unit(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.MISSING_UNIT
    assert "unit" in result.needed


def test_does_not_assume_the_unit_of_a_unitless_number() -> None:
    assert "1.24" in refusal("specific gravity 1.24").detail


@pytest.mark.parametrize(
    "quote",
    ["Density 1.24 MPa", "Density 12 mm", "Density 1.24 g", "Density 7850 kg/m"],
)
def test_refuses_a_unit_of_the_wrong_dimension(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.WRONG_DIMENSION
    assert "density" in result.needed


@pytest.mark.parametrize(
    "quote",
    [
        "Density 0.001 g/cm³",
        "Density 124 g/cm³",
        "Density 1.24 kg/m³",
        "Density 499 kg/m3",
        "Density 20001 kg/m3",
    ],
)
def test_refuses_a_value_outside_the_density_band(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.OUT_OF_BAND
    assert "500" in result.needed
    assert "20000" in result.needed


@pytest.mark.parametrize("quote", ["Density 500 kg/m3", "Density 20000 kg/m3"])
def test_accepts_the_edges_of_the_band(quote: str) -> None:
    assert isinstance(one_quantity(quote, "density"), pint.Quantity)


ALLOWED_SPELLINGS = [
    "1.24 g/cm3",
    "1.24 g/cm\u00b3",
    "1.24 g/cc",
    "1.24 g/mL",
    "1.24 g/ml",
    "1.24 kg/L",
    "1.24 kg/l",
    "1240 kg/m3",
    "1240 kg/m\u00b3",
    "1.24 kg/dm3",
    "1.24 Mg/m3",
    "1.24 t/m3",
    "1.24 tonne/m3",
    "1.24 tonnes/m\u00b3",
    "0.0448 lb/in3",
    "77 lb/ft3",
    "77 lbs/ft\u00b3",
    "1.24 G/CM3",
    "1240 KG/M3",
    "1.24 g / cm3",
    "1.24 g\u00b7cm\u207b\u00b3",
    "1.24 g cm-3",
    "1240 kg\u00b7m\u207b\u00b3",
    "1240 kg m-3",
]


@pytest.mark.parametrize("amount", ALLOWED_SPELLINGS)
def test_reads_every_spelling_on_the_density_allowlist(amount: str) -> None:
    assert 1000.0 <= kg_per_m3(f"Density {amount}") <= 1300.0


@pytest.mark.parametrize(
    "quote",
    [
        "Densidad 7,85 gr/cm3",
        "Density 7.85 gr/cm3",
        "Density 7.85 ton/m3",
        "Density 7.85 tons/m3",
        "Density 1.24 mg/cm3",
        "Density 1.24 MG/M3",
        "Density 1.24 oz/in3",
        "Density 1.24 g/m3",
        "Density 1.24 lb/gal",
        "Density 1.24 g/ccm",
    ],
)
def test_refuses_a_unit_that_is_not_on_the_allowlist(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.UNKNOWN_UNIT
    assert "unit" in result.detail or "unit" in result.needed


@pytest.mark.parametrize(
    "quote",
    [
        "Density 1.14 g/cm3; GF30:1.36 g/cm3",
        "Density 1.14 g/cm3, filled ~1.36 g/cm3",
        "Density 1.24 g/cm3 vs.:1.45 g/cm3",
        "Density 1.24 g/cm3 \u22481.36 g/cm3",
    ],
)
def test_does_not_lose_a_number_glued_to_a_prefix(quote: str) -> None:
    assert refusal(quote).reason is Reason.SEVERAL_QUANTITIES


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density=1.24 g/cm3", 1240.0),
        ("Density:1.24g/cm3", 1240.0),
    ],
)
def test_reads_a_number_glued_to_a_prefix(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize(
    "quote",
    [
        "Density -1.24 g/cm3",
        "Density \u22121240 kg/m3",
        "Density (-7850 kg/m3)",
        "Density 1.24 g/cm3 / -1.45 g/cm3",
    ],
)
def test_refuses_a_negative_value(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.NEGATIVE
    assert "negative" in result.detail


@pytest.mark.parametrize(
    "quote",
    [
        "Density < 1.30 g/cm3",
        "Density > 1.20 g/cm3",
        "Density \u2264 1.30 g/cm3",
        "Density \u22651.20 g/cm3",
        "Density max 1.30 g/cm3",
        "Density min. 1.24 g/cm3",
        "Density 1.24 g/cm3 max",
        "Density 1240 kg/m3 min.",
    ],
)
def test_refuses_a_bound_that_is_not_a_value(quote: str) -> None:
    assert refusal(quote).reason is Reason.BOUND


@pytest.mark.parametrize("quote", ["Density 3 750 kg/m3", "Density 7 850 kg/m3"])
def test_refuses_a_space_grouping_that_could_be_two_numbers(quote: str) -> None:
    assert refusal(quote).reason is Reason.AMBIGUOUS_NUMBER


@pytest.mark.parametrize(
    "amount", ["1.24 g/cm3 \u00b12%", "1.24 g/cm3 \u00b1 0.5 %", "1.24 \u00b12% g/cm3"]
)
def test_a_percent_tolerance_does_not_reach_the_unit(amount: str) -> None:
    assert kg_per_m3(f"Density {amount}") == pytest.approx(1240.0)


@pytest.mark.parametrize(
    "quote",
    [
        "Density 1.24e3 kg/m3",
        "Density 1.24E+03 kg/m3",
        "Density 1.24x10^3 kg/m3",
        "Density 1.24\u00d710\u00b3 kg/m\u00b3",
    ],
)
def test_refuses_scientific_notation_by_name(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.SCIENTIFIC_NOTATION
    assert "scientific notation" in result.detail


def test_refuses_a_quote_over_500_characters() -> None:
    result = refusal("Density 1.24 g/cm3 " + "x" * 500)
    assert result.reason is Reason.TOO_LONG
    assert "500" in result.needed


@pytest.mark.parametrize(
    "quote",
    [
        "1.2 " * 125,
        "1" + ",111" * 120,
        "1" + " 111" * 120,
        "a/b " * 120,
        "\u00b1 " * 240,
        "1.2- " * 100,
    ],
)
def test_a_pathological_quote_is_refused_quickly(quote: str) -> None:
    started = time.perf_counter()
    assert isinstance(one_quantity(quote[:500], "density"), Refusal)
    assert time.perf_counter() - started < 1.0


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
        "Density 8 t m - 3 samples",
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


def test_every_refusal_says_what_the_person_must_supply() -> None:
    quotes = ["", "1.2-1.3 g/cm3", "gravity 1.2", "1.2 mm", "1.2 g/cm3 1.3 kg/m3", "0.1 g/cm3"]
    for quote in quotes:
        result = one_quantity(quote, "density")
        assert isinstance(result, Refusal), quote
        assert result.needed.strip(), quote


def test_every_density_quote_in_the_table_parses_to_the_table_value_or_is_refused() -> None:
    parsed = 0
    for material in load_materials().materials.values():
        cited = material.density
        if not isinstance(cited, Cited):
            continue
        result = one_quantity(cited.source.quote, "density")
        if isinstance(result, Refusal):
            continue
        parsed += 1
        assert magnitude(result, "kg/m^3") == pytest.approx(
            cited.magnitude_in("kg/m^3"), rel=5e-3
        ), material.key
    assert parsed >= 17


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("kaiser-7075-t6", Reason.SEVERAL_QUANTITIES),
        ("cliffs-304", Reason.MISSING_UNIT),
        ("cliffs-316", Reason.MISSING_UNIT),
        ("formlabs-clear-resin-v5", Reason.SEVERAL_QUANTITIES),
        ("plexiglas-gs-0f00", Reason.UNRECOGNISED_TEXT),
        ("plexiglas-xt-0a000", Reason.UNRECOGNISED_TEXT),
    ],
)
def test_refuses_the_table_quotes_that_do_not_state_one_value(key: str, reason: Reason) -> None:
    density = load_materials().materials[key].density
    assert isinstance(density, Cited)
    assert refusal(density.source.quote).reason is reason


@pytest.mark.parametrize("key", ["kaiser-6061-t6", "aurubis-c11000-h02", "polymaker-polymax-pc"])
def test_refuses_the_table_quotes_with_detached_units_or_exponents(key: str) -> None:
    density = load_materials().materials[key].density
    assert isinstance(density, Cited)
    assert isinstance(one_quantity(density.source.quote, "density"), Refusal)


def test_the_scorer_and_the_checks_do_not_import_the_reader() -> None:
    for directory in ("scorecard", "checks"):
        for path in (SRC / directory).rglob("*.py"):
            assert "cad.sources" not in path.read_text(), path
