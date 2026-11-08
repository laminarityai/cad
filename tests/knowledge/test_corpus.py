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
        (GOOD.replace("title: Example", "title: Example PLA data"), "codes"),
        (GOOD.replace("## First", "## M5x0.8 pitch"), "codes"),
        (GOOD.replace("license:", "codes: PLA\nlicense:"), "codes"),
        (GOOD.replace("license:", "codes: [PLA data]\nlicense:"), "codes"),
        (GOOD.replace("title: Example", "title: [unclosed"), "front matter"),
        (GOOD.replace("2026-11-07", "2026-11-07 10:00:00"), "retrieved"),
        (GOOD.replace("Some text.\n", "Some text.\n<!-- page: 9 -->\n"), "page"),
        (GOOD + "## +++\nText.\n", "heading"),
    ],
)
def test_a_bad_file_is_reported(tmp_path: Path, text: str, expected: str) -> None:
    assert expected in problems(tmp_path, text)


def test_a_unit_declares_the_codes_it_is_about(tmp_path: Path) -> None:
    text = GOOD.replace("title: Example", "title: Example PLA data").replace(
        "license:", "codes: [PLA, 'PLA plus']\nlicense:"
    )
    (unit,) = load(write(tmp_path, text)).units.values()
    assert unit.codes == frozenset({"pla", "pla+"})


def test_a_code_named_in_the_text_must_be_declared_or_mentioned(tmp_path: Path) -> None:
    named = GOOD.replace("license:", "codes: [PLA]\nlicense:").replace(
        "Some text.", "PLA is lighter than ABS."
    )
    assert "ABS" in problems(tmp_path, named)
    mentioned = named.replace("license:", "mentions: [ABS]\nlicense:")
    (unit,) = load(write(tmp_path, mentioned)).units.values()
    assert unit.codes == frozenset({"pla"})
    assert unit.mentions == frozenset({"abs"})


def test_a_lowercase_title_that_names_a_known_code_must_declare_it(tmp_path: Path) -> None:
    declared = GOOD.replace("title: Example", "title: Example PLA").replace(
        "license:", "codes: [PLA]\nlicense:"
    )
    write(tmp_path, declared, "a.md")
    write(tmp_path, GOOD.replace("title: Example", "title: polyterra Pla sheet"), "b.md")
    with pytest.raises(InvalidCorpus, match="known code"):
        load(tmp_path)


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


def test_the_seeded_corpus_is_valid_and_answers_its_questions() -> None:
    index = Index(load(CORPUS_PATH))
    assert [h.pointer.id for h in index.search("fresh water density")][:1] == ["kb:water#density"]
    assert [h.pointer.id for h in index.search("PLA+ density")] == ["kb:pla-plus#density"]
    assert [h.pointer.id for h in index.search("PLA density")] == ["kb:pla#density"]
    assert index.search("PETG density") == ()
    assert index.search("M5 clearance hole") == ()
    for query in ("PLA toughness", "PLA layer adhesion", "ordinary PLA", "PolyTerra density"):
        assert index.search(query) == (), query
    for query in ("PLA\uff0b density", "PLA + density", "PLA plus density", "PLA\u207a density"):
        assert [h.pointer.id for h in index.search(query)] == ["kb:pla-plus#density"], query
    assert index.search("plus grade density") == ()
    for query in ("ISO1183 density", "GB/T1033 density", "PLA\u2795 density"):
        assert index.search(query) == (), query


def test_the_scorer_never_loads_the_knowledge_base() -> None:
    code = (
        "import sys, cad.scorecard.score, cad.checks.container.runner; "
        "print([n for n in sys.modules if n.startswith('cad.knowledge')])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
