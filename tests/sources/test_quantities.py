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
        ("Density 7 850 kg/m3", 7850.0),
        ("Density 1.234,5 kg/m3", 1234.5),
        ("Density 1,234.5 kg/m3", 1234.5),
        ("Density 1.24 ± 0.02 g/cm³", 1240.0),
        ("Density [g/cm3] 1.24 ISO 1183", 1240.0),
        ("Density ISO1183, GB/T1033 1.04 g/cm3 at 23°C", 1040.0),
        ("Density ISO 1183 1.24 g/cm³", 1240.0),
        ("Density 7.87 g/cm3 at 20°C", 7870.0),
        ("Density g/cm3 8.5", 8500.0),
        ("Density ISO 1183-1 g/cm³ 1.41", 1410.0),
        ("Density \u03c1 1.19 1.19 1.19 g/cm³ ISO 1183", 1190.0),
        ("Density 1.21 g/cm3 1.21 g/cm3 ASTM D792", 1210.0),
    ],
)
def test_reads_the_one_quantity(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected, rel=2e-3)


def test_keeps_the_unit_written_in_the_quote() -> None:
    result = one_quantity("Density 0.29 lb/in³", "density")
    assert isinstance(result, pint.Quantity)
    assert f"{result.units}" == "pound / inch ** 3"


@pytest.mark.parametrize("quote", ["Density of the part", "", "see the datasheet, page 2"])
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
        "Density 1.24 g/cm³ and specific gravity 1.3",
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
        "Density 1,240 g/cm³",
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


def test_every_refusal_says_what_the_person_must_supply() -> None:
    quotes = ["", "1.2-1.3 g/cm3", "gravity 1.2", "1.2 mm", "1.2 g/cm3 1.3 kg/m3", "1 g/cm3"]
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
    assert parsed >= 15


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("kaiser-6061-t6", Reason.MISSING_UNIT),
        ("kaiser-7075-t6", Reason.SEVERAL_QUANTITIES),
        ("cliffs-304", Reason.MISSING_UNIT),
        ("formlabs-clear-resin-v5", Reason.SEVERAL_QUANTITIES),
        ("aurubis-c11000-h02", Reason.MISSING_UNIT),
        ("polymaker-polymax-pc", Reason.MISSING_UNIT),
    ],
)
def test_refuses_the_table_quotes_that_do_not_state_one_value(key: str, reason: Reason) -> None:
    density = load_materials().materials[key].density
    assert isinstance(density, Cited)
    assert refusal(density.source.quote).reason is reason


def test_the_scorer_and_the_checks_do_not_import_the_reader() -> None:
    for directory in ("scorecard", "checks"):
        for path in (SRC / directory).rglob("*.py"):
            assert "cad.sources" not in path.read_text(), path
