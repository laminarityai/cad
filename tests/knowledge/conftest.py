import json
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import pytest

from cad.knowledge.corpus import load
from cad.knowledge.search import Index


class MakeIndex(Protocol):
    def __call__(
        self,
        files: Mapping[str, str],
        aliases: Mapping[str, list[str]] | None = None,
    ) -> Index: ...


FRONT_MATTER = """---
title: {title}
url: https://example.com/{stem}
retrieved: 2026-11-07
license: own-summary
subject: {stem}
family: true
aliases: {aliases}
---
"""


@pytest.fixture
def make_index(tmp_path: Path) -> MakeIndex:
    """Write one file per stem. Its subject is the stem and its alias is the stem unless given."""

    def build(
        files: Mapping[str, str],
        aliases: Mapping[str, list[str]] | None = None,
    ) -> Index:
        for stem, body in files.items():
            front = FRONT_MATTER.format(
                title=stem.replace("-", " "),
                stem=stem,
                aliases=json.dumps((aliases or {}).get(stem, [stem.replace("-", " ")])),
            )
            (tmp_path / f"{stem}.md").write_text(front + body)
        return Index(load(tmp_path))

    return build
