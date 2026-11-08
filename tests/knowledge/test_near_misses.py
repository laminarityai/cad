# ruff: noqa: RUF001
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
        {"metric": '## Clearance hole\n"M6 clearance hole is 6.6 mm".\n'},
        {"metric": ["M6"]},
        family=True,
    )
    assert index.search("M5 clearance hole") == ()
    assert ids(index.search("M6 clearance hole")) == ["kb:metric#clearance-hole"]


def test_m5_does_not_match_m5x0_8(make_index: MakeIndex) -> None:
    index = make_index(
        {"metric": '## Thread pitch\n"M5x0.8 is the coarse thread pitch".\n'},
        {"metric": ["M5x0.8"]},
        family=True,
    )
    assert index.search("M5 thread pitch") == ()
    assert ids(index.search("M5x0.8 thread pitch")) == ["kb:metric#thread-pitch"]


def test_a_decimal_is_one_word(make_index: MakeIndex) -> None:
    index = make_index(
        {"drill": "## Size 5.5 mm\nThe drill size 5.5 mm suits a tap.\n"}, family=True
    )
    assert index.search("drill size 5 mm") == ()
    assert index.search("drill size 55 mm") == ()
    assert ids(index.search("drill size 5.5 mm")) == ["kb:drill#size-5-5-mm"]


def test_petg_never_returns_pla(make_index: MakeIndex) -> None:
    index = make_index({"pla": "## Density\nPLA density from the data sheet.\n"}, family=True)
    assert index.search("PETG density") == ()
    assert ids(index.search("PLA density")) == ["kb:pla#density"]


def test_pla_never_returns_pla_plus(make_index: MakeIndex) -> None:
    index = make_index(
        {"plus": "## Density\nPLA+ density from the data sheet.\n"}, {"plus": ["PLA+"]}, family=True
    )
    assert index.search("PLA density") == ()
    assert ids(index.search("PLA+ density")) == ["kb:plus#density"]


def test_pla_plus_never_returns_pla(make_index: MakeIndex) -> None:
    index = make_index(
        {"plain": "## Density\nPLA density from the data sheet.\n"}, {"plain": ["PLA"]}, family=True
    )
    assert index.search("PLA+ density") == ()


PETG = {
    "petg": "## Density\nPETG density is 1.27.\n",
    "petg-hf": "## Density\nPETG HF density is 1.29.\n",
    "petg-cf": "## Density\nPETG CF density is 1.25.\n",
}
PETG_ALIASES = {"petg": ["PETG"], "petg-hf": ["PETG HF"], "petg-cf": ["PETG CF", "PETG-CF"]}


def test_petg_basic_hf_and_cf_are_separate_subjects(make_index: MakeIndex) -> None:
    index = make_index(PETG, PETG_ALIASES, family=True)
    assert ids(index.search("PETG HF density")) == ["kb:petg-hf#density"]
    assert ids(index.search("petg cf density")) == ["kb:petg-cf#density"]
    assert ids(index.search("PETG-CF density")) == ["kb:petg-cf#density"]
    assert ids(index.search("PETG density")) == ["kb:petg#density"]
    assert index.search("PETG GF density") == ()


def test_a_base_name_never_returns_a_variant(make_index: MakeIndex) -> None:
    index = make_index({"petg-hf": PETG["petg-hf"]}, {"petg-hf": ["PETG HF"]}, family=True)
    assert index.search("PETG density") == ()
    assert index.search("petg density") == ()
    assert ids(index.search("petg hf density")) == ["kb:petg-hf#density"]


PLASTICS = {
    "pla": "## Density\nPolyTerra density from the data sheet.\n",
    "plus": (
        "## Density\nPolyTerra density from the data sheet.\n\n"
        "## Toughness\nMore layer adhesion and extra toughness than ordinary PLA.\n"
    ),
}
PLASTIC_ALIASES = {"pla": ["PLA"], "plus": ["PLA+"]}


@pytest.mark.parametrize(
    "query",
    ["PLA＋ density", "PLA + density", "PLA plus density", "pla plus density", "PLA⁺ density"],
)
def test_every_spelling_of_pla_plus_is_pla_plus(make_index: MakeIndex, query: str) -> None:
    index = make_index(PLASTICS, PLASTIC_ALIASES, family=True)
    assert ids(index.search(query)) == ["kb:plus#density"]
    assert ids(index.search("PLA density")) == ["kb:pla#density"]


def test_a_spelling_in_an_alias_is_the_same_name(make_index: MakeIndex) -> None:
    index = make_index({"u": "## Density\nPLA＋ density.\n"}, {"u": ["PLA⁺"]}, family=True)
    assert ids(index.search("PLA+ density")) == ["kb:u#density"]
    assert index.search("PLA density") == ()


@pytest.mark.parametrize("query", ["PETG—HF density", "PETG–HF density", "PETG-HF density"])
def test_a_typographic_dash_in_a_name_is_a_hyphen(make_index: MakeIndex, query: str) -> None:
    index = make_index({"u": "## Density\nPETG-HF density.\n"}, {"u": ["PETG-HF"]}, family=True)
    assert ids(index.search(query)) == ["kb:u#density"]
    assert index.search("PETG density") == ()


@pytest.mark.parametrize("query", ["PLA toughness", "PLA layer adhesion", "ordinary PLA"])
def test_a_name_in_a_units_text_is_not_what_the_unit_is_about(
    make_index: MakeIndex, query: str
) -> None:
    assert make_index(PLASTICS, PLASTIC_ALIASES, family=True).search(query) == ()


def test_a_name_that_fits_two_subjects_equally_finds_nothing(make_index: MakeIndex) -> None:
    index = make_index(PLASTICS, PLASTIC_ALIASES, family=True)
    assert index.search("PolyTerra density") == ()
    assert index.search("polyterra data sheet") == ()
    assert index.search("PLA PLA+ density") == ()


COMPARED = {
    "pla": "## Density\nPLA density is 1.24, stiffer than nylon and lower than ABS and Petg.\n"
}


@pytest.mark.parametrize(
    "query",
    [
        "PETG density",
        "petg density",
        "ABS density",
        "abs density",
        "nylon density",
        "Nylon density",
    ],
)
def test_a_material_a_unit_only_compares_against_is_not_what_it_is_about(
    make_index: MakeIndex, query: str
) -> None:
    index = make_index(COMPARED, {"pla": ["PLA"]}, family=True)
    assert index.search(query) == ()
    assert ids(index.search("PLA density")) == ["kb:pla#density"]


def test_a_mention_does_not_remove_recall_for_the_mentioned_words(make_index: MakeIndex) -> None:
    index = make_index(
        {
            "pla": "## HDT\nPLA softens near its HDT; ABS is higher.\n",
            "abs": "## HDT\nABS HDT is higher than PLA's.\n",
        },
        {"pla": ["PLA"], "abs": ["ABS"]},
        family=True,
    )
    assert ids(index.search("PLA HDT")) == ["kb:pla#hdt"]
    assert ids(index.search("ABS HDT")) == ["kb:abs#hdt"]


@pytest.mark.parametrize("query", ["6061 density", "aluminium 6061 density", "316L density"])
def test_a_digit_leading_name_is_exact(make_index: MakeIndex, query: str) -> None:
    index = make_index(
        {
            "al7075": "## Density\nAlloy 7075-T6 density is 2.81 g/cm3, higher than 6061.\n",
            "ss304": "## Density\n304 density is 8.00 g/cm3; 316L is 8.00 too.\n",
        },
        {"al7075": ["7075-T6", "7075"], "ss304": ["304"]},
        family=True,
    )
    assert index.search(query) == ()
    assert ids(index.search("7075 density")) == ["kb:al7075#density"]
    assert ids(index.search("304 density")) == ["kb:ss304#density"]


def test_a_variant_name_the_corpus_lacks_does_not_fall_back_to_a_sibling(
    make_index: MakeIndex,
) -> None:
    index = make_index(
        {"basic": "## Density\nPLA Basic density is 1.26, lighter than PLA Matte.\n"},
        {"basic": ["Bambu PLA Basic", "Bambu Lab PLA Basic"]},
        maker="Bambu Lab",
    )
    assert index.search("PLA Matte density") == ()
    assert index.search("Bambu PLA Matte density") == ()
    assert index.search("PLA Basic density") == ()
    assert ids(index.search("Bambu PLA Basic density")) == ["kb:basic#density"]


def test_the_longest_name_wins_and_two_unrelated_names_conflict(make_index: MakeIndex) -> None:
    index = make_index(PETG, PETG_ALIASES, family=True)
    assert ids(index.search("PETG CF density")) == ["kb:petg-cf#density"]
    assert index.search("PETG HF PETG CF density") == ()


@pytest.mark.parametrize(
    "query",
    [
        "PLA➕ density",
        "PLA✚ density",
        "PLA˖ density",
        "PLA∔ density",
        "PLA (+) density",
        "PLA +/- density",
        "PLA ++ density",
    ],
)
def test_a_plus_the_normal_form_does_not_know_finds_nothing(
    make_index: MakeIndex, query: str
) -> None:
    assert make_index(PLASTICS, PLASTIC_ALIASES, family=True).search(query) == ()


@pytest.mark.parametrize("hidden", ["​", "­", "⁠", "﻿", "‍"])
def test_a_format_character_beside_the_plus_is_ignored(make_index: MakeIndex, hidden: str) -> None:
    index = make_index(PLASTICS, PLASTIC_ALIASES, family=True)
    assert ids(index.search(f"PLA{hidden}+ density")) == ["kb:plus#density"]
    assert ids(index.search(f"PLA {hidden}+ density")) == ["kb:plus#density"]


@pytest.mark.parametrize("query", ["PA12 + density", "PA12 plus density", "pa12+ density"])
def test_a_plus_spelling_joins_a_name_with_digits(make_index: MakeIndex, query: str) -> None:
    index = make_index({"u": "## Density\nPA12+ density.\n"}, {"u": ["PA12+"]}, family=True)
    assert ids(index.search(query)) == ["kb:u#density"]


@pytest.mark.parametrize(
    "query",
    [
        "!PLA density",
        "PLA* density",
        "PLA% density",
        "PLA# density",
        "PLA & density",
        "#PLA density",
    ],
)
def test_punctuation_that_changes_meaning_is_a_word_and_fails_closed(
    make_index: MakeIndex, query: str
) -> None:
    index = make_index(
        {"pla": "## Density\nPLA density from the data sheet.\n"}, {"pla": ["PLA"]}, family=True
    )
    assert index.search(query) == ()


@pytest.mark.parametrize(
    "query", ["PLA density?", "PLA, density", "(PLA) density", '"PLA" density']
)
def test_harmless_punctuation_is_dropped(make_index: MakeIndex, query: str) -> None:
    index = make_index(
        {"pla": "## Density\nPLA density from the data sheet.\n"}, {"pla": ["PLA"]}, family=True
    )
    assert ids(index.search(query)) == ["kb:pla#density"]


SECTIONED = {
    "water": (
        '## Pure water\nThe report says "strictly true only for pure water". '
        "Caveat prose mentions mineral matter and heating.\n"
    )
}


def test_a_word_outside_the_heading_does_not_choose_a_section(make_index: MakeIndex) -> None:
    index = make_index(SECTIONED, {"water": ["water"]}, family=True)
    assert index.search("mineral water") == ()
    assert index.search("water heating") == ()
    assert ids(index.search("water pure")) == ["kb:water#pure-water"]
    assert index.search("water strictly true") == ()


def test_the_source_title_and_quotes_do_not_choose_a_section(make_index: MakeIndex) -> None:
    index = make_index(
        {"polyterra-pla": '## Density\nA quote "1.31 g/cm3".\n'},
        {"polyterra-pla": ["PLA"]},
        family=True,
    )
    assert index.search("Polymaker PLA density") == ()
    assert index.search("PLA polyterra") == ()
    assert index.search("PLA 1.31") == ()
    assert ids(index.search("PLA density")) == ["kb:polyterra-pla#density"]
