from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from cad.knowledge.corpus import load
from cad.knowledge.search import Index

type MakeIndex = Callable[[Mapping[str, str]], Index]

FRONT_MATTER = """---
title: {title}
url: https://example.com/{stem}
retrieved: 2026-11-07
license: own-summary
---
"""


@pytest.fixture
def make_index(tmp_path: Path) -> MakeIndex:
    def build(files: Mapping[str, str]) -> Index:
        for stem, body in files.items():
            title = stem.replace("-", " ")
            (tmp_path / f"{stem}.md").write_text(FRONT_MATTER.format(title=title, stem=stem) + body)
        return Index(load(tmp_path))

    return build
