from dataclasses import fields

from cad.tables.fields import FIELDS
from cad.tables.materials import Material

EXPECTED = {
    "density": ("kg/m^3", 500.0, 20000.0, False),
    "yield_strength": ("MPa", 0.1, 5000.0, False),
    "tensile_strength": ("MPa", 0.1, 5000.0, False),
    "elastic_modulus": ("MPa", 10.0, 500000.0, False),
    "poisson_ratio": ("dimensionless", 0.0, 0.5, True),
}


def test_each_field_has_its_canonical_unit_and_plausible_range() -> None:
    found = {f: (s.canonical_unit, s.low, s.high, s.exclusive) for f, s in FIELDS.items()}
    assert found == EXPECTED


def test_a_material_holds_exactly_the_table_fields() -> None:
    held = [one.name for one in fields(Material) if one.name not in {"key", "name"}]
    assert held == list(FIELDS), "Material in cad/tables/materials.py must match FIELDS"
