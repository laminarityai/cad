from cad.research.fields import SPECS
from cad.tables.materials import DENSITY_RANGE_KG_PER_M3, ELASTIC_MODULUS_RANGE_GPA, FIELD_UNITS

EXPECTED = {
    "density": ("kg/m^3", 500.0, 20000.0, False),
    "yield_strength": ("MPa", 0.1, 5000.0, False),
    "tensile_strength": ("MPa", 0.1, 5000.0, False),
    "elastic_modulus": ("MPa", 10.0, 500000.0, False),
    "poisson_ratio": ("dimensionless", 0.0, 0.5, True),
}


def test_each_field_has_its_canonical_unit_and_plausible_range() -> None:
    found = {f: (s.canonical_unit, s.low, s.high, s.exclusive) for f, s in SPECS.items()}
    assert found == EXPECTED
    assert {field: unit for field, (unit, *_) in EXPECTED.items()} == FIELD_UNITS
    assert DENSITY_RANGE_KG_PER_M3 == (500.0, 20000.0)
    assert ELASTIC_MODULUS_RANGE_GPA == (0.01, 500.0)
