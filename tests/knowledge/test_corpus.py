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
subject: x
aliases: [Example]
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
        (GOOD.replace("subject: x\n", ""), "subject"),
        (GOOD.replace("subject: x", "subject: Not A Key"), "subject"),
        (GOOD.replace("[Example]", "Example"), "aliases"),
        (GOOD.replace("[Example]", "[6061]"), "quote it"),
        (GOOD.replace("[Example]", "[NO]"), "quote it"),
        (GOOD.replace("aliases:", "alias:"), "unknown front matter key 'alias'"),
        (GOOD.replace("subject: x", "subject: x\nmaker: Acme"), "unknown front matter key"),
        (GOOD.replace("subject: x", "subject: other"), "file name"),
        (GOOD.replace("subject: x", "subject: x\nsubject: other"), "duplicate"),
        (GOOD + "```\n## swallowed\nText.\n", "fence"),
        (GOOD + "~~~\n## swallowed\n```\nText.\n", "fence"),
        (GOOD.replace("title: Example", "title: [unclosed"), "front matter"),
        (GOOD.replace("2026-11-07", "2026-11-07 10:00:00"), "retrieved"),
        (GOOD.replace("Some text.\n", "Some text.\n<!-- page: 9 -->\n"), "page"),
        (GOOD + "## +++\nText.\n", "heading"),
    ],
)
def test_a_bad_file_is_reported(tmp_path: Path, text: str, expected: str) -> None:
    assert expected in problems(tmp_path, text)


def test_a_unit_carries_its_subject_and_aliases(tmp_path: Path) -> None:
    text = GOOD.replace("[Example]", "[PolyTerra PLA+, 'Polymaker PolyTerra PLA plus']")
    (unit,) = load(write(tmp_path, text)).units.values()
    assert unit.subject == "x"
    assert unit.aliases == ("PolyTerra PLA+", "Polymaker PolyTerra PLA plus")


def test_aliases_are_optional(tmp_path: Path) -> None:
    (unit,) = load(write(tmp_path, GOOD.replace("aliases: [Example]\n", ""))).units.values()
    assert unit.aliases == ()


def test_a_duplicate_yaml_key_is_refused_wherever_it_sits(tmp_path: Path) -> None:
    assert "duplicate" in problems(tmp_path, GOOD.replace("title: Example", "title: A\ntitle: B"))


def test_a_swallowing_fence_names_the_problem_not_a_missing_heading(tmp_path: Path) -> None:
    assert "unclosed" in problems(tmp_path, GOOD + "```\n## Later\nText.\n")


def test_a_heading_inside_a_code_fence_is_text(tmp_path: Path) -> None:
    text = GOOD + "```\n## not a heading\n```\n"
    (unit,) = load(write(tmp_path, text)).units.values()
    assert "## not a heading" in unit.text


def test_a_byte_order_mark_and_windows_line_endings_are_accepted(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_bytes(b"\xef\xbb\xbf" + GOOD.replace("\n", "\r\n").encode())
    (unit,) = load(tmp_path).units.values()
    assert (unit.pointer.id, unit.pointer.page, unit.text) == ("kb:x#first", "2", "Some text.")


def test_a_file_that_is_not_utf8_is_reported(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_bytes(GOOD.encode() + b"caf\xe9\n")
    with pytest.raises(InvalidCorpus, match="UTF-8"):
        load(tmp_path)


def test_a_file_in_a_subdirectory_is_reported_not_skipped(tmp_path: Path) -> None:
    write(tmp_path, GOOD)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "y.md").write_text(GOOD)
    with pytest.raises(InvalidCorpus, match="subdirector"):
        load(tmp_path)


def test_every_problem_is_collected(tmp_path: Path) -> None:
    message = problems(tmp_path, GOOD.replace("title: Example\n", "").replace("own-summary", "x"))
    assert "title" in message
    assert "license" in message


def first(index: Index, query: str) -> str:
    return index.search(query)[0].pointer.id


def test_the_seeded_corpus_is_valid_and_ranks_its_questions() -> None:
    index = Index(load(CORPUS_PATH))
    assert first(index, "fresh water density") == "kb:water#density"
    assert first(index, "pure water at 4 degrees") == "kb:water#pure-water-at-4-degrees-celsius"
    for query in ("PolyTerra PLA+ density", "PolyTerra PLA plus density", "polyterra pla+ density"):
        assert first(index, query) == "kb:polymaker-polyterra-pla-plus#density", query
    for query in ("PolyTerra PLA density", "Polymaker PolyTerra PLA specific gravity"):
        assert first(index, query) == "kb:polymaker-polyterra-pla#density", query
    assert (
        first(index, "PLA+ toughness")
        == "kb:polymaker-polyterra-pla-plus#how-it-differs-from-the-plain-grade"
    )
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
