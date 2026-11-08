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
        codes: Mapping[str, list[str]] | None = None,
        mentions: Mapping[str, list[str]] | None = None,
    ) -> Index: ...


FRONT_MATTER = """---
title: {title}
url: https://example.com/{stem}
retrieved: 2026-11-07
license: own-summary
codes: {codes}
mentions: {mentions}
---
"""


@pytest.fixture
def make_index(tmp_path: Path) -> MakeIndex:
    def build(
        files: Mapping[str, str],
        codes: Mapping[str, list[str]] | None = None,
        mentions: Mapping[str, list[str]] | None = None,
    ) -> Index:
        for stem, body in files.items():
            title = stem.replace("-", " ")
            front = FRONT_MATTER.format(
                title=title,
                stem=stem,
                codes=json.dumps((codes or {}).get(stem, [])),
                mentions=json.dumps((mentions or {}).get(stem, [])),
            )
            (tmp_path / f"{stem}.md").write_text(front + body)
        return Index(load(tmp_path))

    return build
