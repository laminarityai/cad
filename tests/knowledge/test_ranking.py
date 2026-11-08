# ruff: noqa: RUF001
"""A search returns the best few sections first, each a pointer with its quote."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import pytest

from cad.knowledge.search import MAX_TEXT_CHARS, Hit

if TYPE_CHECKING:
    from conftest import MakeIndex


def ids(hits: Sequence[Hit]) -> list[str]:
    return [hit.pointer.id for hit in hits]


WATER = {
    "water": (
        "## Density\n<!-- page: 244 -->\n"
        'The source says "fresh water density is about 1 g/cm3 near 4 C".\n\n'
        "## Ice\nIce floats on water.\n"
    )
}
WATER_ALIASES = {"water": ["water", "fresh water"]}


def test_a_hit_carries_its_source_page_section_subject_and_quote(make_index: MakeIndex) -> None:
    hit = make_index(WATER, WATER_ALIASES).search("water density")[0]
    assert (hit.pointer.id, hit.subject, hit.pointer.section, hit.pointer.page) == (
        "kb:water#density",
        "water",
        "Density",
        "244",
    )
    assert (hit.pointer.title, hit.pointer.url) == ("water", "https://example.com/water")
    assert hit.pointer.retrieved.isoformat() == "2026-11-07"
    assert '"fresh water density is about 1 g/cm3 near 4 C"' in hit.text
    assert "<!--" not in hit.text


def test_a_long_section_is_cut_and_says_so(make_index: MakeIndex) -> None:
    long = "## Density\n" + "Density words go on and on. " * 200 + "\n"
    (hit,) = make_index({"water": long}).search("water density")
    assert len(hit.text) <= MAX_TEXT_CHARS
    assert hit.text.endswith("[…]")


def test_nothing_matches_and_nothing_returns(make_index: MakeIndex) -> None:
    index = make_index(WATER, WATER_ALIASES)
    assert index.search("quantum chromodynamics lattice") == ()
    assert index.search("") == ()
    assert index.search("what is the") == ()


def test_any_matching_word_returns_candidates(make_index: MakeIndex) -> None:
    index = make_index(WATER, WATER_ALIASES)
    assert set(ids(index.search("water"))) == {"kb:water#density", "kb:water#ice"}
    assert ids(index.search("water viscosity")) != []


def test_k_bounds_the_results_and_defaults_to_five(make_index: MakeIndex) -> None:
    files = {f"m{n}": "## Density\nDensity of this one.\n" for n in range(8)}
    index = make_index(files)
    assert len(index.search("density")) == 5
    assert len(index.search("density", k=2)) == 2


PETG = {
    "petg": "## Density\nPETG density is 1.27.\n",
    "petg-hf": "## Density\nPETG HF is a high-flow PETG. Its density is 1.29.\n",
    "petg-cf": "## Density\nPETG CF density is 1.25.\n",
}
PETG_ALIASES = {"petg": ["PETG"], "petg-hf": ["PETG HF"], "petg-cf": ["PETG CF"]}


@pytest.mark.parametrize(
    ("query", "first"),
    [
        ("PETG HF density", "kb:petg-hf#density"),
        ("petg cf density", "kb:petg-cf#density"),
        ("PETG density", "kb:petg#density"),
    ],
)
def test_the_unit_named_most_closely_ranks_first(
    make_index: MakeIndex, query: str, first: str
) -> None:
    hits = make_index(PETG, PETG_ALIASES).search(query)
    assert ids(hits)[0] == first
    assert len(hits) == 3


def test_a_heading_outranks_a_mention_in_another_units_text(make_index: MakeIndex) -> None:
    index = make_index(
        {
            "pla": "## Density\nPLA density is 1.24, lower than ABS and PETG.\n",
            "abs": "## Density\nThe data sheet value is 1.04.\n",
        },
        {"pla": ["PLA"], "abs": ["ABS"]},
    )
    assert ids(index.search("ABS density")) == ["kb:abs#density", "kb:pla#density"]


def test_a_keys_comment_is_searched_like_the_heading(make_index: MakeIndex) -> None:
    index = make_index(
        {
            "pla": "## Density\n<!-- keys: specific gravity -->\nText.\n\n## Ice\nGravity.\n",
        },
        {"pla": ["PLA"]},
    )
    assert ids(index.search("PLA specific gravity"))[0] == "kb:pla#density"


PLASTICS = {
    "pla": "## Density\nPLA density from the data sheet.\n",
    "plus": "## Density\nPLA+ density from the data sheet.\n",
}
PLASTIC_ALIASES = {"pla": ["PLA"], "plus": ["PLA+"]}


@pytest.mark.parametrize(
    "query",
    [
        "PLA+ density",
        "PLA＋ density",
        "PLA + density",
        "PLA plus density",
        "pla plus density",
        "PLA⁺ density",
        "PLA​+ density",
    ],
)
def test_every_spelling_of_pla_plus_ranks_pla_plus_first(make_index: MakeIndex, query: str) -> None:
    index = make_index(PLASTICS, PLASTIC_ALIASES)
    assert ids(index.search(query))[0] == "kb:plus#density"
    assert ids(index.search("PLA density"))[0] == "kb:pla#density"


@pytest.mark.parametrize(
    "query", ["PETG—HF density", "PETG–HF density", "PETG-HF density", "petg hf DENSITY"]
)
def test_case_and_dashes_do_not_change_the_ranking(make_index: MakeIndex, query: str) -> None:
    assert ids(make_index(PETG, PETG_ALIASES).search(query))[0] == "kb:petg-hf#density"


def test_punctuation_around_a_word_is_dropped(make_index: MakeIndex) -> None:
    index = make_index(PLASTICS, PLASTIC_ALIASES)
    for query in ("PLA density?", "(PLA) density", '"PLA" density', "PLA, density"):
        assert ids(index.search(query))[0] == "kb:pla#density", query


def test_a_decimal_stays_one_word(make_index: MakeIndex) -> None:
    index = make_index({"drill": "## Size 5.5 mm\nThe drill size 5.5 mm suits a tap.\n"})
    assert ids(index.search("5.5")) == ["kb:drill#size-5-5-mm"]
    assert index.search("55") == ()
