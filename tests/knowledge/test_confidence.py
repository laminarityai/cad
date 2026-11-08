from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from conftest import MakeIndex

WATER = {
    "water": (
        '## Density\nThe source says "fresh water density is about 1 g/cm3 near 4 C".\n\n'
        "## Ice\nIce floats on water.\n"
    )
}
WATER_ALIASES = {"water": ["water", "fresh water"]}


def test_a_confident_hit_returns_a_pointer_and_text(make_index: MakeIndex) -> None:
    (hit,) = make_index(WATER, WATER_ALIASES, family=True).search("water density")
    assert hit.pointer.id == "kb:water#density"
    assert hit.pointer.section == "Density"
    assert hit.pointer.url == "https://example.com/water"
    assert "1 g/cm3" in hit.text


def test_no_confident_hit_returns_nothing(make_index: MakeIndex) -> None:
    index = make_index(WATER, WATER_ALIASES, family=True)
    assert index.search("quantum chromodynamics lattice") == ()
    assert index.search("") == ()


def test_a_name_alone_does_not_choose_a_section(make_index: MakeIndex) -> None:
    assert make_index(WATER, WATER_ALIASES, family=True).search("water") == ()


def test_every_word_after_the_name_must_match_the_unit(make_index: MakeIndex) -> None:
    index = make_index(WATER, WATER_ALIASES, family=True)
    assert index.search("water density viscosity") == ()
    assert [h.pointer.id for h in index.search("what is the density of fresh water")] == [
        "kb:water#density"
    ]


def test_a_query_that_names_no_subject_finds_nothing(make_index: MakeIndex) -> None:
    assert make_index(WATER, WATER_ALIASES, family=True).search("PETG fresh density") == ()
    assert make_index(WATER, WATER_ALIASES, family=True).search("fresh density") == ()


def test_a_heading_matches_whatever_its_case(make_index: MakeIndex) -> None:
    index = make_index(
        {"water": "## Zinc heat capacity\nText.\n\n## Alpha Heat Capacity\nText.\n"}, family=True
    )
    hits = index.search("WATER alpha HEAT capacity")
    assert [h.pointer.id for h in hits] == ["kb:water#alpha-heat-capacity"]


@pytest.mark.parametrize(
    ("heading", "asked", "other"),
    [
        ("Density (Mg/m3)", "PLA density Mg/m3", "PLA density mg/m3"),
        ("Density (mg/m3)", "PLA DENSITY mg/m3", "PLA density Mg/m3"),
        ("Modulus (MPa)", "PLA modulus MPa", "PLA modulus mPa"),
        ("Viscosity (mPa s)", "pla Viscosity mPa s", "PLA viscosity MPa s"),
        ("Load (kN)", "PLA load kN", "PLA load KN"),
    ],
)
def test_a_unit_symbol_matches_only_in_its_own_case(
    make_index: MakeIndex, heading: str, asked: str, other: str
) -> None:
    index = make_index({"pla": f"## {heading}\nText.\n"}, {"pla": ["PLA"]}, family=True)
    assert len(index.search(asked)) == 1
    assert index.search(other) == ()


def test_a_declared_key_keeps_the_case_of_its_unit_symbol(make_index: MakeIndex) -> None:
    body = "## Density\n<!-- keys: density Mg/m3 -->\nText.\n"
    index = make_index({"pla": body}, {"pla": ["PLA"]}, family=True)
    assert len(index.search("PLA density Mg/m3")) == 1
    assert index.search("PLA density mg/m3") == ()
