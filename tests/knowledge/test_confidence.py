from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conftest import MakeIndex

WATER = {
    "water": (
        '## Density\nThe source says "fresh water density is about 1 g/cm3 near 4 C".\n\n'
        "## Ice\nIce floats on water.\n"
    )
}


def test_a_confident_hit_returns_a_pointer_and_text(make_index: MakeIndex) -> None:
    (hit,) = make_index(WATER).search("water density")
    assert hit.pointer.id == "kb:water#density"
    assert hit.pointer.section == "Density"
    assert hit.pointer.url == "https://example.com/water"
    assert "1 g/cm3" in hit.text


def test_no_confident_hit_returns_nothing(make_index: MakeIndex) -> None:
    index = make_index(WATER)
    assert index.search("quantum chromodynamics lattice") == ()
    assert index.search("") == ()


def test_a_name_alone_does_not_choose_a_section(make_index: MakeIndex) -> None:
    assert make_index(WATER).search("water") == ()


def test_every_word_after_the_name_must_match_the_unit(make_index: MakeIndex) -> None:
    index = make_index(WATER)
    assert index.search("water density viscosity") == ()
    assert [h.pointer.id for h in index.search("what is the density of fresh water")] == [
        "kb:water#density"
    ]


def test_a_query_that_names_no_subject_finds_nothing(make_index: MakeIndex) -> None:
    assert make_index(WATER).search("PETG fresh density") == ()
    assert make_index(WATER).search("fresh density") == ()


def test_hits_are_ordered_by_id_and_ignore_case(make_index: MakeIndex) -> None:
    index = make_index(
        {"water": '## Zinc heat\n"water heat capacity"\n\n## Alpha heat\n"Water Heat Capacity"\n'}
    )
    hits = index.search("WATER heat capacity")
    assert [h.pointer.id for h in hits] == ["kb:water#alpha-heat", "kb:water#zinc-heat"]
