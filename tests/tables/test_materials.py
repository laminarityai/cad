import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from cad.tables.materials import (
    FIELD_UNITS,
    TABLE_PATH,
    InvalidTable,
    Known,
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
    assert {
        "cliffs-304",
        "kaiser-6061-t6",
        "polymaker-polylite-abs",
        "prusament-petg",
        "prusament-pla",
    } <= set(table.materials)


def test_every_value_is_cited_or_unknown() -> None:
    material = load_materials().get_material("prusament-pla")
    assert isinstance(material.density, Known)
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


def elastic(modulus: str, poisson: str) -> Callable[[Row], None]:
    def edit(row: Row) -> None:
        source = row["density"]["source"]
        row["elastic_modulus"] = {"value": modulus, "source": source}
        row["poisson_ratio"] = {"value": poisson, "source": source}

    return edit


def test_a_cited_modulus_and_poisson_ratio_load_in_their_units(tmp_path: Path) -> None:
    path = write_edited_table(tmp_path, "prusament-pla", elastic("3.5 GPa", "0.36"))
    material = load_materials(path).get_material("prusament-pla")
    assert isinstance(material.elastic_modulus, Known)
    assert isinstance(material.poisson_ratio, Known)
    assert material.elastic_modulus.magnitude_in("MPa") == pytest.approx(3500)
    assert material.poisson_ratio.magnitude_in("dimensionless") == pytest.approx(0.36)


@pytest.mark.parametrize(
    ("modulus", "poisson", "problem"),
    [
        ("5 MPa", "0.3", "elastic_modulus 5 MPa is outside the plausible range 0.01 to 500 GPa"),
        ("600 GPa", "0.3", "elastic_modulus 600 GPa is outside the plausible range"),
        ("3.5 GPa", "0.5", "poisson_ratio 0.5 is not above 0 and below 0.5"),
        ("3.5 GPa", "0", "poisson_ratio 0 is not above 0 and below 0.5"),
        ("3.5 GPa", "-0.1", "poisson_ratio -0.1 is not above 0 and below 0.5"),
        ("3.5 GPa", "0.3 MPa", "poisson_ratio '0.3 MPa': Cannot convert"),
        ("0.5 GPa", "0.3", "yield_strength 51 MPa is not below 0.1 of elastic_modulus 0.5 GPa"),
    ],
)
def test_rejects_an_implausible_elastic_constant(
    tmp_path: Path, modulus: str, poisson: str, problem: str
) -> None:
    assert problem in problems_after(tmp_path, "prusament-pla", elastic(modulus, poisson))


def test_a_git_row_may_not_take_a_projects_key(tmp_path: Path) -> None:
    def edit(row: Row) -> None:
        row["key"] = "project-prusament-pla"

    assert "kept for a project's own rows" in problems_after(tmp_path, "prusament-pla", edit)


def test_a_material_the_table_lacks_is_named_as_the_projects_own_row() -> None:
    table = load_materials()
    assert table.row_key("prusament-pla") == "prusament-pla"
    assert table.row_key("acme-silk-pla") == "project-acme-silk-pla"
    assert table.row_key("project-acme-silk-pla") == "project-acme-silk-pla"
    assert table.row_key("project-project-acme-silk-pla") == "project-acme-silk-pla"
    assert table.row_key("project-prusament-pla") == "prusament-pla"
    assert table.row_key("project-project-prusament-pla") == "prusament-pla"
    blank = table.get_material("project-acme-silk-pla")
    assert {blank.value(field) for field in FIELD_UNITS} == {Unknown()}


def test_a_second_load_reuses_the_parse_and_an_edited_table_is_read_again(tmp_path: Path) -> None:
    first = load_materials()
    assert load_materials() is first
    edited = load_materials(
        write_edited_table(tmp_path, "prusament-pla", lambda row: row.update(name="renamed"))
    )
    assert edited.version != first.version
    assert edited.materials["prusament-pla"].name == "renamed"
    assert load_materials().materials["prusament-pla"].name == first.materials["prusament-pla"].name
