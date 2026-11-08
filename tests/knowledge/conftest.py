import json
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import pytest

from cad.knowledge.corpus import Corpus, load
from cad.knowledge.search import Index

FRONT_MATTER = """---
title: {title}
url: https://example.com/{stem}
retrieved: 2026-11-07
license: own-summary
subject: {stem}
aliases: {aliases}
---
"""
FIRST_BODY_LINE = 9
"""FRONT_MATTER is eight lines, so a body starts on line 9."""


class MakeCorpus(Protocol):
    def __call__(
        self, files: Mapping[str, str], aliases: Mapping[str, list[str]] | None = None
    ) -> Corpus: ...


class MakeIndex(Protocol):
    def __call__(
        self, files: Mapping[str, str], aliases: Mapping[str, list[str]] | None = None
    ) -> Index: ...


@pytest.fixture
def make_corpus(tmp_path: Path) -> MakeCorpus:
    """Write one file per stem and load every file written so far.

    Its subject is the stem, and its alias is the stem with spaces unless given.
    """

    def build(files: Mapping[str, str], aliases: Mapping[str, list[str]] | None = None) -> Corpus:
        for stem, body in files.items():
            front = FRONT_MATTER.format(
                title=stem.replace("-", " "),
                stem=stem,
                aliases=json.dumps((aliases or {}).get(stem, [stem.replace("-", " ")])),
            )
            (tmp_path / f"{stem}.md").write_text(front + body)
        return load(tmp_path)

    return build


@pytest.fixture
def make_index(make_corpus: MakeCorpus) -> MakeIndex:
    def build(files: Mapping[str, str], aliases: Mapping[str, list[str]] | None = None) -> Index:
        return Index(make_corpus(files, aliases))

    return build
