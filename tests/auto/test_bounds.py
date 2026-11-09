from typing import Any, Final

import pytest
from pydantic import TypeAdapter

from cad.auto.bounds import bounds_conflicts
from cad.auto.model import Read
from cad.briefs.model import BriefId, BriefSpan, Requirement, RequirementId, Target
from cad.tables.materials import load_materials

TABLE: Final = load_materials()
TARGET: Final = TypeAdapter[Target](Target)
CUBE: Final = {"kind": "envelope", "edges": [{"magnitude": 20, "unit": "mm"}] * 3}
PLA: Final = {"kind": "made_of", "material": "prusament-pla"}


def grams(kind: str, magnitude: float) -> dict[str, Any]:
    return {"kind": kind, "mass": {"magnitude": magnitude, "unit": "g"}}


def volume(comparator: str, cm3: float) -> dict[str, Any]:
    return {
        "kind": "measure_limit",
        "check_id": "mass",
        "measure": "volume",
        "comparator": comparator,
        "limit": {"magnitude": cm3, "unit": "cm^3"},
    }


def brief(*targets: dict[str, Any]) -> tuple[Requirement, ...]:
    return tuple(
        Requirement(
            id=RequirementId(f"r{n}"),
            brief_id=BriefId("b" * 16),
            target=TARGET.validate_python(target),
            origin=BriefSpan(start=0, end=1),
        )
        for n, target in enumerate(targets, start=1)
    )


def test_a_20_mm_pla_cube_cannot_weigh_50_g() -> None:
    [found] = bounds_conflicts(brief(CUBE, PLA, grams("min_mass", 50)), TABLE)
    assert found.quantity == "mass"
    assert found.statement == (
        "min_mass 50 g > density(prusament-pla) 1.24 g/cm³ \N{MULTIPLICATION SIGN} "
        "envelope 8 cm³ = 9.92 g"
    )
    assert found.requirements == ("r3", "r2", "r1")
    assert found.reads == (
        Read(material_key="prusament-pla", field="density", value="1.24 g/cm³", basis="table"),
    )


@pytest.mark.parametrize(
    ("targets", "quantity", "statement"),
    [
        ((grams("min_mass", 60), grams("max_mass", 50)), "mass", "min_mass 60 g > max_mass 50 g"),
        (
            (CUBE, volume("at_least", 9)),
            "volume",
            "volume at least 9 cm³ > envelope 8 cm³",
        ),
        (
            (volume("at_most", 5), volume("at_least", 6)),
            "volume",
            "volume at least 6 cm³ > volume at most 5 cm³",
        ),
    ],
)
def test_bounds_on_one_quantity_that_cannot_both_hold_conflict(
    targets: tuple[dict[str, Any], ...], quantity: str, statement: str
) -> None:
    [found] = bounds_conflicts(brief(*targets), TABLE)
    assert (found.quantity, found.statement) == (quantity, statement)


@pytest.mark.parametrize(
    "targets",
    [
        (CUBE, PLA, grams("min_mass", 9)),
        (CUBE, PLA, grams("min_mass", 9.92), grams("max_mass", 50)),
        (CUBE, {"kind": "made_of", "material": "pla"}, grams("min_mass", 50)),
        (CUBE, grams("min_mass", 50)),
        (grams("min_mass", 50), grams("max_mass", 50)),
    ],
    ids=["reachable", "at the limit", "unknown density", "no material", "equal bounds"],
)
def test_a_consistent_brief_or_an_unknown_value_proves_nothing(
    targets: tuple[dict[str, Any], ...],
) -> None:
    assert bounds_conflicts(brief(*targets), TABLE) == ()
