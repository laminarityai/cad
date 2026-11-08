"""The section step: the words after the name must equal a heading or a declared key."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import pytest

from cad.knowledge.corpus import InvalidCorpus
from cad.knowledge.search import Hit

if TYPE_CHECKING:
    from conftest import MakeIndex


def ids(hits: Sequence[Hit]) -> list[str]:
    return [hit.pointer.id for hit in hits]


def test_a_heading_with_more_words_is_not_the_plain_property(make_index: MakeIndex) -> None:
    index = make_index(
        {
            "pla": (
                '## Density\n"Density 1.24 g/cm3".\n\n'
                '## Density of PLA-CF\n"PLA-CF density 1.30 g/cm3".\n\n'
                '## Density of seawater aged samples\n"Aged density 1.27 g/cm3".\n'
            )
        },
        {"pla": ["PLA"]},
        family=True,
    )
    assert ids(index.search("PLA density")) == ["kb:pla#density"]
    assert ids(index.search("PLA CF density")) == ["kb:pla#density-of-pla-cf"]


def test_a_heading_about_another_material_is_not_this_ones(make_index: MakeIndex) -> None:
    index = make_index(
        {
            "polylite-asa": (
                '## ABS density for comparison\n"ABS 1.04 g/cm3".\n\n'
                '## Density\n"Density 1.07 g/cm3".\n'
            )
        },
        {"polylite-asa": ["PolyLite ASA"]},
        maker="Polymaker",
        line="PolyLite",
    )
    assert ids(index.search("PolyLite ASA density")) == ["kb:polylite-asa#density"]


def test_a_query_must_name_the_whole_heading(make_index: MakeIndex) -> None:
    index = make_index(
        {"w": "## Fresh density\nText.\n\n## Fresh heat\nText.\n"}, {"w": ["water"]}, family=True
    )
    assert index.search("water fresh") == ()
    assert ids(index.search("water fresh heat")) == ["kb:w#fresh-heat"]


def test_the_subjects_own_name_in_a_heading_is_read_like_the_query(make_index: MakeIndex) -> None:
    index = make_index({"w": "## Pure water\nText.\n"}, {"w": ["water"]}, family=True)
    assert ids(index.search("pure water")) == ["kb:w#pure-water"]
    assert ids(index.search("water pure")) == ["kb:w#pure-water"]


HDT = '## Heat deflection temperature\n<!-- keys: HDT, heat deflection -->\n"HDT 57 °C".\n'


def test_a_declared_key_chooses_its_section(make_index: MakeIndex) -> None:
    index = make_index({"pla": HDT}, {"pla": ["PLA"]}, family=True)
    for query in ("PLA HDT", "PLA heat deflection", "PLA heat deflection temperature"):
        assert ids(index.search(query)) == ["kb:pla#heat-deflection-temperature"], query
    assert index.search("PLA HDT temperature") == ()
    assert index.search("PLA deflection") == ()


def test_a_key_comment_is_not_part_of_the_text(make_index: MakeIndex) -> None:
    (hit,) = make_index({"pla": HDT}, {"pla": ["PLA"]}, family=True).search("PLA HDT")
    assert hit.text == '"HDT 57 °C".'


def test_a_key_and_a_page_comment_sit_together(make_index: MakeIndex) -> None:
    body = "## Density\n<!-- page: 2 -->\n<!-- keys: densities -->\nText.\n"
    (hit,) = make_index({"pla": body}, {"pla": ["PLA"]}, family=True).search("PLA densities")
    assert (hit.pointer.page, hit.text) == ("2", "Text.")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("## Density\nA.\n\n## Densities\n<!-- keys: density -->\nB.\n", "both answer to"),
        ("## Density\n<!-- keys: HDT -->\nA.\n\n## HDT\nB.\n", "both answer to"),
        ("## Density\n<!-- keys: SG -->\nA.\n\n## Mass\n<!-- keys: sg -->\nB.\n", "both answer"),
        ("## Density of the PLA\nA.\n\n## Density\nB.\n", "both answer to"),
        ("## Density\n<!-- keys: the, densities -->\nA.\n", "stopwords"),
        ("## Density\n<!-- keys: densities, , SG -->\nA.\n", "empty key"),
        ("## Density\n<!-- keys: SG -->\n<!-- keys: densities -->\nA.\n", "more than one keys"),
        ("## PLA\nA.\n", "can never be found"),
    ],
)
def test_a_section_name_that_cannot_choose_one_unit_is_refused(
    make_index: MakeIndex, body: str, expected: str
) -> None:
    with pytest.raises(InvalidCorpus, match=expected):
        make_index({"pla": body}, {"pla": ["PLA"]}, family=True)
