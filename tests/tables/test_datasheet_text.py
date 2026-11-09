from dataclasses import replace
from pathlib import Path

import pytest

from cad.tables.datasheet_text import citations, cover, quote_problems, render, text_path
from cad.tables.materials import TABLE_PATH, UNITS, Known, MaterialsTable, load_materials

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


def test_a_value_its_quote_does_not_write_names_the_row(tmp_path: Path) -> None:
    path = tmp_path / "materials.yaml"
    text = TABLE_PATH.read_text(encoding="utf-8")
    path.write_text(text.replace("value: 1.24 g/cm^3", "value: 1.99 g/cm^3", 1), encoding="utf-8")
    [problem] = quote_problems(load_materials(path))
    assert problem.startswith("prusament-pla density: 1.99 is not written in its quote")


def problems_with_pla(
    table: MaterialsTable, store: Path, field: str, value: str, quote: str
) -> list[str]:
    """The problems once prusament-pla's `field` reads `value` and cites `quote`, with the quote
    stored in its datasheet's text."""
    pla = table.get_material("prusament-pla")
    known = pla.value(field)
    assert isinstance(known, Known)
    changed_value = Known(UNITS.Quantity(value), replace(known.source, quote=quote))
    changed = replace(
        table, materials={**table.materials, pla.key: replace(pla, **{field: changed_value})}
    )
    url = known.source.url
    pages = [c.quote for c in citations(changed) if c.url == url]
    text_path(url, store).write_text(render(url, pages), encoding="utf-8")
    return quote_problems(changed, store)


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("1.24 g/cm^3", "Densité 1,24 g/cm3"),
        ("1240 kg/m^3", "Density 1 240 kg/m3"),
        ("1240 kg/m^3", "Density 1,240 kg/m3"),
        ("1.2 g/cm^3", "Density 1.20 g/cm3"),
    ],
)
def test_a_value_written_in_another_number_format_passes(
    table: MaterialsTable, store: Path, value: str, quote: str
) -> None:
    assert problems_with_pla(table, store, "density", value, quote) == []


@pytest.mark.parametrize(
    ("field", "value", "quote"),
    [
        ("density", "1.24 g/cm^3", "Density [g/cm³] 1.24"),
        ("density", "1.24 g/cm^3", "Density 1.24 g/cm^3"),
        ("yield_strength", "51 MPa", "Yield strength 51 N/mm2"),
        ("yield_strength", "51 MPa", "Yield strength [MPa] 51"),
    ],
)
def test_a_unit_written_in_an_equivalent_spelling_passes(
    table: MaterialsTable, store: Path, field: str, value: str, quote: str
) -> None:
    assert problems_with_pla(table, store, field, value, quote) == []


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("51 MPa", "Yield strength 51 mPa"),
        ("51 MPa", "Yield strength 51 ksi"),
        ("51 MPa", "Yield strength 51"),
        ("51 ksi", "Yield strength 51 MPa"),
    ],
)
def test_a_unit_its_quote_does_not_write_names_the_row(
    table: MaterialsTable, store: Path, value: str, quote: str
) -> None:
    [problem] = problems_with_pla(table, store, "yield_strength", value, quote)
    assert problem.startswith("prusament-pla yield_strength: its unit")
    assert "is not written in its quote" in problem


def test_changing_a_rows_unit_to_ksi_fails_the_check(tmp_path: Path) -> None:
    """The mutations that slipped past a check reading only the magnitude: 109.3 MPa read as
    109.3 ksi is 753.6 MPa."""
    path = tmp_path / "materials.yaml"
    text = TABLE_PATH.read_text(encoding="utf-8")
    for row in ("109.3", "276", "310"):
        text = text.replace(f"value: {row} MPa\n", f"value: {row} ksi\n", 1)
    path.write_text(text, encoding="utf-8")
    problems = quote_problems(load_materials(path))
    assert [problem.split(" is not written")[0] for problem in problems] == [
        "kaiser-6061-t6 yield_strength: its unit ksi",
        "kaiser-6061-t6 tensile_strength: its unit ksi",
        "polymaker-fiberon-pa6-cf20 tensile_strength: its unit ksi",
    ]


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
