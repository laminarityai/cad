from pathlib import Path

import pytest

from cad.tables.datasheet_text import quote_problems
from cad.tables.fasteners import load_fasteners
from cad.tables.materials import InvalidTable, load_materials
from cad.tables.tolerances import (
    TABLE_PATH,
    OutsideClass,
    TolerancesTable,
    UnknownClass,
    load_tolerances,
)


@pytest.fixture(scope="module")
def table() -> TolerancesTable:
    return load_tolerances()


def edited(tmp_path: Path, old: str, new: str) -> Path:
    path = tmp_path / "tolerances.yaml"
    text = TABLE_PATH.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("key", "diameter", "low", "high"),
    [
        ("H7", 8, 8, 8.015),
        ("H8", 8, 8, 8.022),
        ("H9", 8, 8, 8.036),
        ("H11", 8, 8, 8.09),
        ("H7", 6, 6, 6.012),
        ("H7", 6.001, 6.001, 6.016),
        ("H7", 50, 50, 50.025),
        ("H11", 50, 50, 50.16),
        ("H7", 1, 1, 1.01),
        ("ISO 2768-f", 8, 7.9, 8.1),
        ("ISO 2768-m", 8, 7.8, 8.2),
        ("ISO 2768-c", 8, 7.5, 8.5),
        ("ISO 2768-c", 3, 2.8, 3.2),
        ("ISO 2768-c", 3.01, 2.71, 3.31),
        ("ISO 2768-f", 0.5, 0.45, 0.55),
    ],
)
def test_a_class_gives_the_band_of_the_row_that_holds_the_diameter(
    table: TolerancesTable, key: str, diameter: float, low: float, high: float
) -> None:
    band = table.limits(key, diameter)
    assert (band.low_mm, band.high_mm) == pytest.approx((low, high))


@pytest.mark.parametrize("key", ["h7", "H6", "H 7", "ISO 2768-v", "ISO 2768", "m", " H7"])
def test_a_key_that_is_not_a_class_is_refused(table: TolerancesTable, key: str) -> None:
    with pytest.raises(UnknownClass):
        table.get(key)


@pytest.mark.parametrize(
    ("key", "diameter", "covers"),
    [
        ("H7", 150, "over 0 mm up to 120 mm"),
        ("ISO 2768-m", 0.4, "from 0.5 mm up to 400 mm"),
        ("ISO 2768-m", 450, "from 0.5 mm up to 400 mm"),
    ],
)
def test_a_diameter_outside_every_range_names_the_range_the_class_covers(
    table: TolerancesTable, key: str, diameter: float, covers: str
) -> None:
    with pytest.raises(OutsideClass, match=covers):
        table.limits(key, diameter)


def test_the_committed_quotes_are_on_the_stored_pages(table: TolerancesTable) -> None:
    assert quote_problems(load_materials(), tolerances=table, fasteners=load_fasteners()) == []


def test_a_limit_its_quote_does_not_write_names_the_row(tmp_path: Path) -> None:
    path = edited(tmp_path, "up_to_mm: 10, limit: 15,", "up_to_mm: 10, limit: 16,")
    [problem] = quote_problems(
        load_materials(), tolerances=load_tolerances(path), fasteners=load_fasteners()
    )
    assert problem.startswith("H7 10 mm limit: 16.0 is not written in its quote")


def test_a_range_its_header_does_not_write_names_the_row(tmp_path: Path) -> None:
    path = edited(
        tmp_path,
        "over_mm: 120, up_to_mm: 400, limit: 0.2,",
        "over_mm: 120, up_to_mm: 401, limit: 0.2,",
    )
    problems = quote_problems(
        load_materials(), tolerances=load_tolerances(path), fasteners=load_fasteners()
    )
    assert any(
        one.startswith("ISO 2768-f 401 mm up_to_mm: 401.0 is not written") for one in problems
    )


def test_a_quote_that_is_on_no_stored_page_names_the_row(tmp_path: Path) -> None:
    path = edited(
        tmp_path,
        '"6 10 0 .4 0 .6 1 .0 1 .5 2 .5 4 6 9 15',
        '"6 10 0 .4 0 .6 1 .0 1 .5 2 .5 4 6 9 16',
    )
    problems = quote_problems(
        load_materials(), tolerances=load_tolerances(path), fasteners=load_fasteners()
    )
    assert any(
        one.startswith("H7 10 mm limit: the quote is not in the stored text") for one in problems
    )


def test_ranges_that_do_not_meet_are_refused(tmp_path: Path) -> None:
    path = edited(
        tmp_path, "over_mm: 3, up_to_mm: 6, limit: 12,", "over_mm: 4, up_to_mm: 6, limit: 12,"
    )
    with pytest.raises(InvalidTable, match="H7: the range up to 3 mm must meet the next"):
        load_tolerances(path)


def test_a_limit_that_shrinks_as_the_size_grows_is_refused(tmp_path: Path) -> None:
    path = edited(tmp_path, "limit: 25, quote:", "limit: 5, quote:")
    with pytest.raises(InvalidTable, match="the limit at 50 mm is below"):
        load_tolerances(path)


def test_a_key_twice_is_refused(tmp_path: Path) -> None:
    path = edited(tmp_path, "- key: H8\n", "- key: H7\n")
    with pytest.raises(InvalidTable, match="H7: key appears twice"):
        load_tolerances(path)
