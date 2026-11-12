from dataclasses import fields
from decimal import Decimal

import pytest

from cad.tables.fields import FIELDS, FieldSpec
from cad.tables.materials import Material

EXPECTED = {
    "density": ("kg/m^3", Decimal(500), Decimal(20000), False),
    "yield_strength": ("MPa", Decimal("0.1"), Decimal(5000), False),
    "tensile_strength": ("MPa", Decimal("0.1"), Decimal(5000), False),
    "elastic_modulus": ("MPa", Decimal(10), Decimal(500000), False),
    "poisson_ratio": ("dimensionless", Decimal(0), Decimal("0.5"), True),
}


def test_each_field_has_its_canonical_unit_and_plausible_range() -> None:
    found = {f: (s.canonical_unit, s.low, s.high, s.exclusive) for f, s in FIELDS.items()}
    assert found == EXPECTED


def test_a_material_holds_exactly_the_table_fields() -> None:
    held = [one.name for one in fields(Material) if one.name not in {"key", "name"}]
    assert held == list(FIELDS), "Material in cad/tables/materials.py must match FIELDS"


NUDGE = Decimal("0.000001")


@pytest.mark.parametrize("spec", FIELDS.values(), ids=list(FIELDS))
def test_a_field_admits_the_bounds_its_message_states_and_refuses_just_outside(
    spec: FieldSpec,
) -> None:
    for bound in (spec.low, spec.high):
        assert spec.admits(bound) is not spec.exclusive, (bound, spec.accepts)
    assert not spec.admits(spec.low - NUDGE)
    assert not spec.admits(spec.high + NUDGE)
    assert spec.admits(spec.low + NUDGE)
    assert spec.admits(spec.high - NUDGE)
