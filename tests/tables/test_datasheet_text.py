from pathlib import Path

import pytest

from cad.tables.datasheet_text import citations, cover, quote_problems, render, text_path
from cad.tables.materials import MaterialsTable, load_materials

REGEN = "uv run python tools/regen_datasheet_text.py"
DENSITY = "Density [g/cm3] 1.24 ISO 1183"
POISSON = "Poisson's ratio 0.35"
PAGES = ["Cover page", DENSITY, "Tensile Yield Strength [MPa] 51"]


@pytest.fixture(scope="module")
def table() -> MaterialsTable:
    return load_materials()


@pytest.fixture
def store(tmp_path: Path, table: MaterialsTable) -> Path:
    """Each cited url stored with one page per quote, as the regen script would keep them."""
    path = tmp_path / "datasheet_text"
    path.mkdir()
    pages: dict[str, list[str]] = {}
    for citation in citations(table):
        pages.setdefault(citation.url, []).append(citation.quote)
    for url, quotes in pages.items():
        text_path(url, path).write_text(render(url, quotes), encoding="utf-8")
    return path


def first_quote(table: MaterialsTable, key: str) -> tuple[str, str]:
    citation = next(c for c in citations(table) if c.key == key)
    return citation.url, citation.quote


def test_committed_text_holds_every_quote(table: MaterialsTable) -> None:
    assert quote_problems(table) == []


def test_a_store_that_holds_every_quote_passes(table: MaterialsTable, store: Path) -> None:
    assert quote_problems(table, store) == []


def test_a_row_without_stored_text_names_the_row_and_the_regen_script(
    table: MaterialsTable, store: Path
) -> None:
    url, _ = first_quote(table, "prusament-pla")
    text_path(url, store).unlink()
    problems = quote_problems(table, store)
    assert problems
    assert all(problem.startswith("prusament-pla ") and REGEN in problem for problem in problems)


def test_a_quote_not_in_the_stored_text_names_the_row_and_the_quote(
    table: MaterialsTable, store: Path
) -> None:
    url, quote = first_quote(table, "prusament-pla")
    text_path(url, store).write_text(render(url, ["Density 1.24"]), encoding="utf-8")
    problems = quote_problems(table, store)
    assert any(
        problem.startswith("prusament-pla density: the quote is not in the stored text")
        and repr(quote) in problem
        and REGEN in problem
        for problem in problems
    )


def test_a_quote_split_across_two_pages_is_not_found(table: MaterialsTable, store: Path) -> None:
    url, quote = first_quote(table, "prusament-pla")
    half = len(quote) // 2
    text_path(url, store).write_text(render(url, [quote[:half], quote[half:]]), encoding="utf-8")
    assert any(p.startswith("prusament-pla density:") for p in quote_problems(table, store))


def test_text_no_row_cites_is_reported(table: MaterialsTable, store: Path) -> None:
    gone = "https://example.com/gone.pdf"
    text_path(gone, store).write_text(render(gone, ["x"]), encoding="utf-8")
    [problem] = quote_problems(table, store)
    assert "no row cites its url" in problem
    assert REGEN in problem


def test_cover_keeps_only_pages_with_a_quote_and_reads_the_next_tool_only_if_needed() -> None:
    reads: list[str] = []

    def first() -> list[str]:
        reads.append("first")
        return PAGES

    def second() -> list[str]:
        reads.append("second")
        return [f"Page two says {POISSON}"]

    assert cover([DENSITY], [first, second]) == ([DENSITY], [])
    assert reads == ["first"]

    kept, left = cover([DENSITY, POISSON, "absent"], [first, second])
    assert kept == [DENSITY, f"Page two says {POISSON}"]
    assert left == ["absent"]


def test_a_quote_cannot_start_partway_through_a_number() -> None:
    assert cover(["960 kg/m3"], [lambda: ["Density 8960 kg/m3"]]) == ([], ["960 kg/m3"])
