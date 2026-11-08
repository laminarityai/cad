"""A section starts where a reviewer sees a heading in the rendered file, and only there."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import pytest

from cad.knowledge.corpus import InvalidCorpus
from cad.knowledge.search import Hit, Index

if TYPE_CHECKING:
    from conftest import MakeIndex

DENSITY = '## Density\n"Density 1.24 g/cm3".\n\n'
FIRST_BODY_LINE = 10
"""conftest writes nine front matter lines for a family file, so the body starts on line 10."""


def ids(hits: Sequence[Hit]) -> list[str]:
    return [hit.pointer.id for hit in hits]


def load(make_index: MakeIndex, body: str) -> Index:
    return make_index({"pla": DENSITY + body}, {"pla": ["PLA"]}, family=True)


@pytest.mark.parametrize(
    "heading",
    [
        " ## Melting point",
        "   ## Melting point",
        "##\tMelting point",
        "# Melting point",
        "### Melting point",
        "###### Melting point",
        "#",
        "##",
        "## Melting point ##",
        "## Melting point #",
        "> ## Melting point",
        "- ## Melting point",
        "1. ### Melting point",
        "Melting point\n---",
        "Melting point\n=",
        "Melting point\n  ------  ",
    ],
)
def test_a_heading_in_any_other_form_is_refused_with_its_line(
    make_index: MakeIndex, heading: str
) -> None:
    with pytest.raises(InvalidCorpus) as error:
        load(make_index, f"{heading}\n\"Melting point 160 C\".\n")
    assert f"pla.md: line {FIRST_BODY_LINE + 3}:" in str(error.value)
    assert "heading" in str(error.value)


@pytest.mark.parametrize(
    "line",
    [
        "##Melting point",
        "####### Melting point",
        "    ## Melting point",
        "#5 nozzle",
        "Melting point\n- - -",
        "\n---",
        "\n===",
    ],
)
def test_a_line_that_renders_as_text_stays_in_the_section(make_index: MakeIndex, line: str) -> None:
    index = load(make_index, f"{line}\nMore text.\n")
    (hit,) = index.search("PLA density")
    assert line.strip() in hit.text


@pytest.mark.parametrize(
    "inside",
    ["# Melting point", "  ## Melting point", "### Melting point", "Melting point\n---"],
)
def test_a_heading_inside_a_code_fence_is_text(make_index: MakeIndex, inside: str) -> None:
    index = load(make_index, f"```\n{inside}\n```\n")
    (hit,) = index.search("PLA density")
    assert inside in hit.text


def test_a_fence_closes_only_on_a_fence_at_least_as_long(make_index: MakeIndex) -> None:
    index = load(make_index, "````\n```\n## Melting point\n````\n")
    (hit,) = index.search("PLA density")
    assert "## Melting point" in hit.text
    assert index.search("PLA melting point") == ()


def test_inline_code_of_three_backticks_is_not_a_fence(make_index: MakeIndex) -> None:
    index = load(make_index, "```x``` is inline code.\n\n## Melting point\nText.\n")
    assert ids(index.search("PLA melting point")) == ["kb:pla#melting-point"]


def test_a_fence_indented_four_spaces_is_not_a_fence(make_index: MakeIndex) -> None:
    index = load(make_index, "    ```\n\n## Melting point\nText.\n\n    ```\n")
    assert ids(index.search("PLA melting point")) == ["kb:pla#melting-point"]


def test_the_one_accepted_form_still_starts_a_section(make_index: MakeIndex) -> None:
    index = load(make_index, "##  Melting point  \nText.\n")
    assert ids(index.search("PLA melting point")) == ["kb:pla#melting-point"]


def test_a_keys_comment_inside_a_code_fence_is_text(make_index: MakeIndex) -> None:
    body = "## Density\n```\n<!-- keys: hardness -->\n<!-- page: 3 -->\n```\nText.\n"
    index = make_index({"pla": body}, {"pla": ["PLA"]}, family=True)
    assert index.search("PLA hardness") == ()
    (hit,) = index.search("PLA density")
    assert "<!-- keys: hardness -->" in hit.text
    assert hit.pointer.page is None


@pytest.mark.parametrize(
    "comment",
    [
        "<!-- keys densities -->",
        "<!-- Keys: sg -->",
        "<!-- KEYS: sg -->",
        "<!-- keys: >1 g/cm3 -->",
        "<!-- keys -->",
        "<!-- keys sg, specific gravity -->",
    ],
)
def test_a_malformed_keys_comment_is_refused(make_index: MakeIndex, comment: str) -> None:
    with pytest.raises(InvalidCorpus, match="keys comment"):
        make_index({"pla": f"## Density\n{comment}\nText.\n"}, {"pla": ["PLA"]}, family=True)


def test_a_keys_comment_without_spaces_is_well_formed(make_index: MakeIndex) -> None:
    index = make_index({"pla": "## Density\n<!--keys:sg-->\nText.\n"}, {"pla": ["PLA"]}, family=True)
    assert ids(index.search("PLA sg")) == ["kb:pla#density"]
