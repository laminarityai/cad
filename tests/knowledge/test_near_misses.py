from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import pytest

from cad.knowledge.search import Hit

if TYPE_CHECKING:
    from conftest import MakeIndex


def ids(hits: Sequence[Hit]) -> list[str]:
    return [hit.pointer.id for hit in hits]


def test_m5_returns_nothing_when_only_m6_is_present(make_index: MakeIndex) -> None:
    index = make_index(
        {"metric": "## Clearance holes\nM6 clearance hole is 6.6 mm.\n"}, {"metric": ["M6"]}
    )
    assert index.search("M5 clearance hole") == ()
    assert ids(index.search("M6 clearance hole")) == ["kb:metric#clearance-holes"]


def test_m5_does_not_match_m5x0_8(make_index: MakeIndex) -> None:
    index = make_index(
        {"metric": "## Pitch\nM5x0.8 is the coarse thread pitch.\n"}, {"metric": ["M5x0.8"]}
    )
    assert index.search("M5 thread pitch") == ()
    assert ids(index.search("M5x0.8 thread pitch")) == ["kb:metric#pitch"]


def test_a_decimal_is_one_token(make_index: MakeIndex) -> None:
    index = make_index({"drill": "## Sizes\nThe drill size 5.5 mm suits a tap.\n"})
    assert index.search("drill size 5 mm") == ()
    assert index.search("drill size 55 mm") == ()
    assert ids(index.search("drill size 5.5 mm")) == ["kb:drill#sizes"]


def test_petg_never_returns_pla(make_index: MakeIndex) -> None:
    index = make_index({"pla": "## Density\nPLA density from the data sheet.\n"}, {"pla": ["PLA"]})
    assert index.search("PETG density") == ()
    assert ids(index.search("PLA density")) == ["kb:pla#density"]


def test_pla_never_returns_pla_plus(make_index: MakeIndex) -> None:
    index = make_index(
        {"plus": "## Density\nPLA+ density from the data sheet.\n"}, {"plus": ["PLA+"]}
    )
    assert index.search("PLA density") == ()
    assert ids(index.search("PLA+ density")) == ["kb:plus#density"]


def test_pla_plus_never_returns_pla(make_index: MakeIndex) -> None:
    index = make_index(
        {"plain": "## Density\nPLA density from the data sheet.\n"}, {"plain": ["PLA"]}
    )
    assert index.search("PLA+ density") == ()


def test_petg_basic_hf_and_cf_stay_apart(make_index: MakeIndex) -> None:
    index = make_index(
        {
            "petg-basic": "## Density\nBambu PETG Basic density.\n",
            "petg-hf": "## Density\nBambu PETG HF density.\n",
            "petg-cf": "## Density\nBambu PETG CF density.\n",
        },
        {"petg-basic": ["PETG"], "petg-hf": ["PETG", "HF"], "petg-cf": ["PETG", "CF"]},
    )
    assert ids(index.search("Bambu PETG HF density")) == ["kb:petg-hf#density"]
    assert ids(index.search("Bambu PETG CF density")) == ["kb:petg-cf#density"]
    assert ids(index.search("Bambu PETG Basic density")) == ["kb:petg-basic#density"]
    assert index.search("Bambu PETG GF density") == ()


def test_lowercase_queries_do_not_drift_to_a_sibling(make_index: MakeIndex) -> None:
    index = make_index(
        {
            "pla": "## Density\nPLA density from the data sheet.\n",
            "petg-hf": "## Density\nBambu PETG HF density.\n",
        },
        {"pla": ["PLA"], "petg-hf": ["PETG", "HF"]},
    )
    assert index.search("pla+ density") == ()
    assert index.search("petg basic density") == ()
    assert index.search("petg cf density") == ()
    assert ids(index.search("petg hf density")) == ["kb:petg-hf#density"]


PLASTICS = {
    "pla": "## Density\nPolyTerra density from the data sheet.\n",
    "plus": (
        "## Density\nPolyTerra density from the data sheet.\n\n"
        "## Toughness\nMore layer adhesion and extra toughness than ordinary PLA.\n"
    ),
}
PLASTIC_CODES = {"pla": ["PLA"], "plus": ["PLA+"]}


@pytest.mark.parametrize(
    "query",
    [
        "PLA\uff0b density",
        "PLA + density",
        "PLA plus density",
        "pla plus density",
        "PLA\u207a density",
    ],
)
def test_every_spelling_of_pla_plus_is_pla_plus(make_index: MakeIndex, query: str) -> None:
    index = make_index(PLASTICS, PLASTIC_CODES)
    assert ids(index.search(query)) == ["kb:plus#density"]
    assert ids(index.search("PLA density")) == ["kb:pla#density"]


def test_a_spelling_in_the_unit_is_the_same_code(make_index: MakeIndex) -> None:
    index = make_index({"u": "## Density\nPLA\uff0b density.\n"}, {"u": ["PLA\u207a"]})
    assert ids(index.search("PLA+ density")) == ["kb:u#density"]
    assert index.search("PLA density") == ()


@pytest.mark.parametrize(
    "query", ["PETG\u2014HF density", "PETG\u2013HF density", "PETG-HF density"]
)
def test_a_typographic_dash_in_a_code_is_a_hyphen(make_index: MakeIndex, query: str) -> None:
    index = make_index({"u": "## Density\nPETG-HF density.\n"}, {"u": ["PETG-HF"]})
    assert ids(index.search(query)) == ["kb:u#density"]
    assert index.search("PETG density") == ()


@pytest.mark.parametrize("query", ["PLA toughness", "PLA layer adhesion", "ordinary PLA"])
def test_a_code_in_a_units_text_is_not_a_code_it_is_about(
    make_index: MakeIndex, query: str
) -> None:
    assert make_index(PLASTICS, PLASTIC_CODES).search(query) == ()


def test_a_query_with_a_code_still_finds_the_unit_about_it(make_index: MakeIndex) -> None:
    index = make_index(PLASTICS, PLASTIC_CODES)
    assert ids(index.search("PLA+ toughness")) == ["kb:plus#toughness"]
    assert ids(index.search("pla+ layer adhesion")) == ["kb:plus#toughness"]


def test_a_query_with_no_code_and_two_answers_returns_nothing(make_index: MakeIndex) -> None:
    index = make_index(PLASTICS, PLASTIC_CODES)
    assert index.search("PolyTerra density") == ()
    assert index.search("polyterra data sheet") == ()


def test_a_query_with_no_code_may_hit_several_units_about_one_thing(
    make_index: MakeIndex,
) -> None:
    index = make_index({"w": "## Density\nFresh water density.\n\n## Heat\nFresh water heat.\n"})
    assert ids(index.search("fresh water")) == ["kb:w#density", "kb:w#heat"]
