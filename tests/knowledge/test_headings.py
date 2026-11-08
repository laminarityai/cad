"""A section starts where a reviewer sees a heading in the rendered file, and only there."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cad.knowledge.corpus import Corpus, InvalidCorpus

if TYPE_CHECKING:
    from conftest import MakeCorpus

DENSITY = '## Density\n"Density 1.24 g/cm3".\n\n'
FIRST_BODY_LINE = 9
"""conftest writes eight front matter lines, so the body starts on line 9."""


def load(make_corpus: MakeCorpus, body: str) -> Corpus:
    return make_corpus({"pla": DENSITY + body}, {"pla": ["PLA"]})


def sections(corpus: Corpus) -> list[str]:
    return sorted(corpus.units)


def density_text(corpus: Corpus) -> str:
    return corpus.units["kb:pla#density"].text


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
    make_corpus: MakeCorpus, heading: str
) -> None:
    with pytest.raises(InvalidCorpus) as error:
        load(make_corpus, f'{heading}\n"Melting point 160 C".\n')
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
def test_a_line_that_renders_as_text_stays_in_the_section(
    make_corpus: MakeCorpus, line: str
) -> None:
    corpus = load(make_corpus, f"{line}\nMore text.\n")
    assert sections(corpus) == ["kb:pla#density"]
    assert line.strip() in density_text(corpus)


@pytest.mark.parametrize(
    "inside",
    ["# Melting point", "  ## Melting point", "### Melting point", "Melting point\n---"],
)
def test_a_heading_inside_a_code_fence_is_text(make_corpus: MakeCorpus, inside: str) -> None:
    corpus = load(make_corpus, f"```\n{inside}\n```\n")
    assert sections(corpus) == ["kb:pla#density"]
    assert inside in density_text(corpus)


def test_a_fence_closes_only_on_a_fence_at_least_as_long(make_corpus: MakeCorpus) -> None:
    corpus = load(make_corpus, "````\n```\n## Melting point\n````\n")
    assert sections(corpus) == ["kb:pla#density"]
    assert "## Melting point" in density_text(corpus)


def test_inline_code_of_three_backticks_is_not_a_fence(make_corpus: MakeCorpus) -> None:
    corpus = load(make_corpus, "```x``` is inline code.\n\n## Melting point\nText.\n")
    assert sections(corpus) == ["kb:pla#density", "kb:pla#melting-point"]


def test_a_fence_indented_four_spaces_is_not_a_fence(make_corpus: MakeCorpus) -> None:
    corpus = load(make_corpus, "    ```\n\n## Melting point\nText.\n\n    ```\n")
    assert sections(corpus) == ["kb:pla#density", "kb:pla#melting-point"]


def test_the_one_accepted_form_still_starts_a_section(make_corpus: MakeCorpus) -> None:
    corpus = load(make_corpus, "##  Melting point  \nText.\n")
    assert sections(corpus) == ["kb:pla#density", "kb:pla#melting-point"]


def test_a_keys_or_page_comment_inside_a_code_fence_is_text(make_corpus: MakeCorpus) -> None:
    body = "## Density\n```\n<!-- keys: hardness -->\n<!-- page: 3 -->\n```\nText.\n"
    unit = make_corpus({"pla": body}, {"pla": ["PLA"]}).units["kb:pla#density"]
    assert "<!-- keys: hardness -->" in unit.text
    assert unit.keys == ()
    assert unit.pointer.page is None


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
def test_a_malformed_keys_comment_is_refused(make_corpus: MakeCorpus, comment: str) -> None:
    with pytest.raises(InvalidCorpus, match="keys comment"):
        make_corpus({"pla": f"## Density\n{comment}\nText.\n"}, {"pla": ["PLA"]})


def test_a_keys_comment_is_read_and_left_out_of_the_text(make_corpus: MakeCorpus) -> None:
    body = "## Density\n<!--keys:sg, specific gravity-->\nText.\n"
    unit = make_corpus({"pla": body}, {"pla": ["PLA"]}).units["kb:pla#density"]
    assert unit.keys == ("sg", "specific gravity")
    assert unit.text == "Text."
