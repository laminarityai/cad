import subprocess
import sys
from pathlib import Path

import pytest

from cad.knowledge.corpus import CORPUS_PATH, InvalidCorpus, load
from cad.knowledge.search import Index

GOOD = """---
title: Example
url: https://example.com/x
retrieved: 2026-11-07
license: own-summary
---
## First
<!-- page: 2 -->
Some text.
"""


def write(tmp_path: Path, text: str, name: str = "x.md") -> Path:
    (tmp_path / name).write_text(text)
    return tmp_path


def problems(tmp_path: Path, text: str) -> str:
    with pytest.raises(InvalidCorpus) as error:
        load(write(tmp_path, text))
    return str(error.value)


def test_a_unit_carries_its_source_page_and_section(tmp_path: Path) -> None:
    corpus = load(write(tmp_path, GOOD))
    (pointer,) = (unit.pointer for unit in corpus.units.values())
    assert (pointer.id, pointer.title, pointer.page, pointer.section) == (
        "kb:x#first",
        "Example",
        "2",
        "First",
    )
    assert pointer.retrieved.isoformat() == "2026-11-07"


def test_the_version_changes_with_any_byte(tmp_path: Path) -> None:
    first = load(write(tmp_path, GOOD)).version
    assert load(write(tmp_path, GOOD + "More.\n")).version != first


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (GOOD.replace("title: Example\n", ""), "title"),
        (GOOD.replace("https://example.com/x", "file:///etc/passwd"), "url"),
        (GOOD.replace("2026-11-07", "yesterday"), "retrieved"),
        (GOOD.replace("own-summary", "all-rights-reserved"), "license"),
        (GOOD.replace("<!-- page: 2 -->", "<!-- page: two -->"), "page"),
        (GOOD + "## First\nAgain.\n", "duplicate"),
        (GOOD.replace("Some text.\n", ""), "empty"),
        (GOOD.replace("---\n## First", "---\nstray\n## First"), "before the first"),
        ("## No front matter\ntext\n", "front matter"),
    ],
)
def test_a_bad_file_is_reported(tmp_path: Path, text: str, expected: str) -> None:
    assert expected in problems(tmp_path, text)


def test_every_problem_is_collected(tmp_path: Path) -> None:
    message = problems(tmp_path, GOOD.replace("title: Example\n", "").replace("own-summary", "x"))
    assert "title" in message
    assert "license" in message


def test_the_seeded_corpus_is_valid_and_answers_its_questions() -> None:
    index = Index(load(CORPUS_PATH))
    assert [h.pointer.id for h in index.search("fresh water density")][:1] == ["kb:water#density"]
    assert [h.pointer.id for h in index.search("PLA+ density")] == ["kb:pla-plus#density"]
    assert [h.pointer.id for h in index.search("PLA density")] == ["kb:pla#density"]
    assert index.search("PETG density") == ()
    assert index.search("M5 clearance hole") == ()


def test_the_scorer_never_loads_the_knowledge_base() -> None:
    code = (
        "import sys, cad.scorecard.score, cad.checks.container.runner; "
        "print([n for n in sys.modules if n.startswith('cad.knowledge')])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
