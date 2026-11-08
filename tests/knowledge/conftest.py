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
        *,
        family: bool = False,
        maker: str | None = None,
        line: str | None = None,
    ) -> Index: ...


FRONT_MATTER = """---
title: {title}
url: https://example.com/{stem}
retrieved: 2026-11-07
license: own-summary
subject: {stem}
{brand}aliases: {aliases}
---
"""


@pytest.fixture
def make_index(tmp_path: Path) -> MakeIndex:
    """Write one file per stem and load every file written so far.

    Its subject is the stem and its alias is the stem unless given. Each file of one call is
    `family: true` when `family` is set, and otherwise branded by `maker` and `line`; a branded
    file with no maker is refused by the loader. Call it twice to mix family and branded files.
    """

    def build(
        files: Mapping[str, str],
        aliases: Mapping[str, list[str]] | None = None,
        *,
        family: bool = False,
        maker: str | None = None,
        line: str | None = None,
    ) -> Index:
        brand = "family: true\n" if family else ""
        brand += f"maker: {maker}\n" if maker else ""
        brand += f"line: {line}\n" if line else ""
        for stem, body in files.items():
            front = FRONT_MATTER.format(
                title=stem.replace("-", " "),
                stem=stem,
                brand=brand,
                aliases=json.dumps((aliases or {}).get(stem, [stem.replace("-", " ")])),
            )
            (tmp_path / f"{stem}.md").write_text(front + body)
        return Index(load(tmp_path))

    return build
