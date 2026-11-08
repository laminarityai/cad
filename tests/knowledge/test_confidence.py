from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conftest import MakeIndex

WATER = {
    "water": (
        "## Density\nFresh water density is about 1 g/cm3 near 4 C.\n\n"
        "## Ice\nIce floats on water.\n"
    )
}


def test_a_confident_hit_returns_a_pointer_and_text(make_index: MakeIndex) -> None:
    (hit,) = make_index(WATER).search("fresh water density")
    assert hit.pointer.id == "kb:water#density"
    assert hit.pointer.section == "Density"
    assert hit.pointer.url == "https://example.com/water"
    assert "1 g/cm3" in hit.text


def test_no_confident_hit_returns_nothing(make_index: MakeIndex) -> None:
    index = make_index(WATER)
    assert index.search("quantum chromodynamics lattice") == ()
    assert index.search("") == ()


def test_one_content_word_alone_is_not_confident(make_index: MakeIndex) -> None:
    assert make_index(WATER).search("water") == ()


def test_every_content_word_must_match(make_index: MakeIndex) -> None:
    index = make_index(WATER)
    assert index.search("water density viscosity") == ()
    assert [h.pointer.id for h in index.search("what is the density of fresh water")] == [
        "kb:water#density"
    ]


def test_an_identifier_must_match_even_when_the_words_do(make_index: MakeIndex) -> None:
    assert make_index(WATER).search("PETG fresh water density") == ()


def test_hits_are_ordered_by_id_and_ignore_case(make_index: MakeIndex) -> None:
    index = make_index(
        {
            "b": "## Heat\nwater heat capacity\n",
            "a": "## Heat\nWater Heat Capacity density\n",
        }
    )
    hits = index.search("WATER heat capacity")
    assert [h.pointer.id for h in hits] == ["kb:a#heat", "kb:b#heat"]
