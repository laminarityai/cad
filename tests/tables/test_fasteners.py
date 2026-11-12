from pathlib import Path

import pytest

from cad.tables.datasheet_text import quote_problems
from cad.tables.fasteners import (
    TABLE_PATH,
    FastenersTable,
    UnknownFastener,
    load_fasteners,
)
from cad.tables.materials import InvalidTable, load_materials


@pytest.fixture(scope="module")
def table() -> FastenersTable:
    return load_fasteners()


def edited(tmp_path: Path, old: str, new: str) -> Path:
    path = tmp_path / "fasteners.yaml"
    text = TABLE_PATH.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


def test_the_sizes_are_read_by_exact_key(table: FastenersTable) -> None:
    m5 = table.get("M5")
    assert (m5.clearance.close_mm, m5.clearance.medium_mm, m5.clearance.coarse_mm) == (
        5.3,
        5.5,
        5.8,
    )
    assert (m5.tapped.minor_min_mm, m5.tapped.tap_drill_mm, m5.tapped.minor_max_mm) == (
        4.134,
        4.2,
        4.334,
    )


@pytest.mark.parametrize("key", ["m5", "M 5", "M5 ", "5", "M7"])
def test_a_key_that_is_not_a_row_is_refused(table: FastenersTable, key: str) -> None:
    with pytest.raises(UnknownFastener):
        table.get(key)


def test_the_committed_quotes_are_on_the_stored_pages(table: FastenersTable) -> None:
    assert quote_problems(load_materials(), fasteners=table) == []


def test_a_number_its_quote_does_not_write_names_the_row(tmp_path: Path) -> None:
    path = edited(tmp_path, "medium_mm: 5.5\n", "medium_mm: 5.6\n")
    [problem] = quote_problems(load_materials(), fasteners=load_fasteners(path))
    assert problem.startswith("M5 clearance medium_mm: 5.6 is not written in its quote")


def test_a_quote_that_is_on_no_stored_page_names_the_row(tmp_path: Path) -> None:
    path = edited(tmp_path, 'quote: "M5 5,3 5,5 5,8"', 'quote: "M5 5,3 5,5 5,9"')
    problems = quote_problems(load_materials(), fasteners=load_fasteners(path))
    assert any(
        one.startswith("M5 clearance close_mm: the quote is not in the stored text")
        for one in problems
    )


def test_a_clearance_hole_below_the_bolt_is_refused(tmp_path: Path) -> None:
    path = edited(tmp_path, "close_mm: 5.3\n", "close_mm: 4.9\n")
    with pytest.raises(InvalidTable, match="M5: clearance must satisfy"):
        load_fasteners(path)


def test_a_tap_drill_outside_the_minor_diameter_is_refused(tmp_path: Path) -> None:
    path = edited(tmp_path, "tap_drill_mm: 4.2\n", "tap_drill_mm: 4.6\n")
    with pytest.raises(InvalidTable, match="M5: tapped must satisfy"):
        load_fasteners(path)


def test_a_key_twice_is_refused(tmp_path: Path) -> None:
    path = edited(tmp_path, "- key: M6\n", "- key: M5\n")
    with pytest.raises(InvalidTable, match="M5: key appears twice"):
        load_fasteners(path)


def test_a_row_without_a_source_is_refused(tmp_path: Path) -> None:
    path = edited(
        tmp_path,
        "      source:\n        <<: *clearance\n",
        "      sauce:\n        <<: *clearance\n",
    )
    with pytest.raises(InvalidTable):
        load_fasteners(path)
