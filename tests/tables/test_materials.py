import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from cad.tables.materials import (
    TABLE_PATH,
    Cited,
    InvalidTable,
    Unknown,
    UnknownMaterial,
    load_materials,
)

type Row = dict[str, Any]


def write_edited_table(tmp_path: Path, key: str, edit: Callable[[Row], None]) -> Path:
    document = yaml.safe_load(TABLE_PATH.read_bytes())
    rows: list[Row] = document["materials"]
    edit(next(row for row in rows if row["key"] == key))
    path = tmp_path / "materials.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True))
    return path


def problems_after(tmp_path: Path, key: str, edit: Callable[[Row], None]) -> str:
    with pytest.raises(InvalidTable) as raised:
        load_materials(write_edited_table(tmp_path, key, edit))
    return str(raised.value)


def test_table_loads_with_sha256_version() -> None:
    table = load_materials()
    assert table.version == hashlib.sha256(TABLE_PATH.read_bytes()).hexdigest()
    assert sorted(table.materials) == [
        "cliffs-304",
        "kaiser-6061-t6",
        "polymaker-polylite-abs",
        "prusament-petg",
        "prusament-pla",
    ]


def test_every_value_is_cited_or_unknown() -> None:
    material = load_materials().get_material("prusament-pla")
    assert isinstance(material.density, Cited)
    assert material.density.magnitude_in("kg/m^3") == pytest.approx(1240)
    assert material.density.source.standard == "ISO 1183"
    assert material.tensile_strength == Unknown()


def test_version_changes_with_one_digit(tmp_path: Path) -> None:
    def edit(row: Row) -> None:
        row["density"]["value"] = "1.25 g/cm^3"

    edited = load_materials(write_edited_table(tmp_path, "prusament-pla", edit))
    assert edited.version != load_materials().version


@pytest.mark.parametrize("key", ["pla", "PLA", "prusament-pla ", " prusament-pla", "Prusament PLA"])
def test_lookup_misses_any_key_not_spelled_as_in_the_file(key: str) -> None:
    with pytest.raises(UnknownMaterial, match="no material with key"):
        load_materials().get_material(key)


def test_petg_never_returns_pla_values() -> None:
    table = load_materials()
    with pytest.raises(UnknownMaterial):
        table.get_material("petg")
    petg = table.get_material("prusament-petg")
    pla = table.get_material("prusament-pla")
    assert petg.name == "Prusament PETG"
    assert petg.density != pla.density
    assert petg.yield_strength != pla.yield_strength


def test_rejects_value_without_source(tmp_path: Path) -> None:
    def edit(row: Row) -> None:
        del row["yield_strength"]["source"]

    assert "kaiser-6061-t6: yield_strength has no source" in problems_after(
        tmp_path, "kaiser-6061-t6", edit
    )


def test_rejects_unit_pint_cannot_convert(tmp_path: Path) -> None:
    def edit(row: Row) -> None:
        row["density"]["value"] = "1.24 furlong"

    problems = problems_after(tmp_path, "prusament-pla", edit)
    assert "prusament-pla: density '1.24 furlong': Cannot convert from 'furlong'" in problems


def test_rejects_unit_pint_does_not_define(tmp_path: Path) -> None:
    def edit(row: Row) -> None:
        row["density"]["value"] = "1.24 blorp"

    assert "'blorp' is not defined" in problems_after(tmp_path, "prusament-pla", edit)


def test_rejects_yield_above_tensile(tmp_path: Path) -> None:
    def edit(row: Row) -> None:
        row["yield_strength"]["value"] = "320 MPa"

    assert (
        "kaiser-6061-t6: yield_strength 320 MPa is above tensile_strength 310 MPa"
        in problems_after(tmp_path, "kaiser-6061-t6", edit)
    )


def test_compares_strengths_across_units(tmp_path: Path) -> None:
    def edit(row: Row) -> None:
        row["yield_strength"]["value"] = "660 MPa"

    assert "cliffs-304: yield_strength 660 MPa is above tensile_strength 95 ksi" in (
        problems_after(tmp_path, "cliffs-304", edit)
    )


def test_rejects_implausible_density(tmp_path: Path) -> None:
    def edit(row: Row) -> None:
        row["density"]["value"] = "50 kg/m^3"

    assert (
        "prusament-petg: density 50 kg/m³ is outside the plausible range 500 to 20000 kg/m³"
        in problems_after(tmp_path, "prusament-petg", edit)
    )


def test_rejects_duplicate_key(tmp_path: Path) -> None:
    def edit(row: Row) -> None:
        row["key"] = "prusament-pla"

    assert "prusament-pla: key appears twice" in problems_after(tmp_path, "prusament-petg", edit)


def test_rejects_key_with_trailing_space(tmp_path: Path) -> None:
    def edit(row: Row) -> None:
        row["key"] = "prusament-pla "

    assert "'prusament-pla ': key must be" in problems_after(tmp_path, "prusament-pla", edit)
