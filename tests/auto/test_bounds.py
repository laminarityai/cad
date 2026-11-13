from typing import Any, Final

import pytest
from pydantic import TypeAdapter

from cad.auto.bounds import bounds_conflicts, unweighed
from cad.auto.model import Read
from cad.briefs.model import BriefId, Requirement, RequirementId, Target
from cad.briefs.origins import BriefSpan
from cad.tables.materials import load_materials

TABLE: Final = load_materials()
TARGET: Final = TypeAdapter[Target](Target)
CUBE: Final = {"kind": "envelope", "edges": [{"magnitude": 20, "unit": "mm"}] * 3}
PLA: Final = {"kind": "made_of", "material": "prusament-pla"}


def grams(kind: str, magnitude: float) -> dict[str, Any]:
    return {"kind": kind, "mass": {"magnitude": magnitude, "unit": "g"}}


def limit(
    check_id: str, measure: str, comparator: str, value: float, unit: str = "dimensionless"
) -> dict[str, Any]:
    return {
        "kind": "measure_limit",
        "check_id": check_id,
        "measure": measure,
        "comparator": comparator,
        "limit": {"magnitude": value, "unit": unit},
    }


def volume(comparator: str, cm3: float) -> dict[str, Any]:
    return limit("mass", "volume", comparator, cm3, "cm^3")


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
        "The mass must be at least 50 g, but Prusament PLA at 1.24 g/cm³ weighs 9.92 g "
        "filling the whole 20 x 20 x 20 mm box (8 cm³)"
    )
    assert found.requirements == ("r3", "r2", "r1")
    assert found.reads == (
        Read(material_key="prusament-pla", field="density", value="1.24 g/cm³", basis="table"),
    )


@pytest.mark.parametrize(
    ("targets", "quantity", "statement"),
    [
        (
            (grams("min_mass", 60), grams("max_mass", 50)),
            "mass",
            "The mass must be at least 60 g, but the mass must be at most 50 g",
        ),
        (
            (CUBE, volume("at_least", 9)),
            "volume",
            "The volume of material in the part must be at least 9 cm³, but the whole "
            "20 x 20 x 20 mm box holds 8 cm³",
        ),
        (
            (volume("at_most", 5), volume("at_least", 6)),
            "volume",
            "The volume of material in the part must be at least 6 cm³, but the volume of "
            "material in the part must be at most 5 cm³",
        ),
        (
            (
                limit("holes", "hole_count", "at_least", 5),
                limit("holes", "hole_count", "at_most", 3),
            ),
            "holes:hole_count",
            "The number of round holes in the part must be at least 5, but the number of round "
            "holes in the part must be at most 3",
        ),
        (
            (
                limit("min_wall", "min_wall", "at_least", 3, "mm"),
                limit("min_wall", "min_wall", "at_most", 2, "mm"),
            ),
            "min_wall:min_wall",
            "The thickness of the part's thinnest wall must be at least 3 mm, but the thickness "
            "of the part's thinnest wall must be at most 2 mm",
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


def test_a_material_with_no_density_yet_is_named_as_not_checked() -> None:
    asa = {"kind": "made_of", "material": "asa"}
    found = unweighed(brief(CUBE, asa, grams("min_mass", 50)), TABLE)
    assert found is not None
    assert found.statement == (
        "asa has no density yet, so whether the mass can be at least 50 g within the whole "
        "20 x 20 x 20 mm box (8 cm³) is not checked until its density is researched"
    )
    assert found.requirements == ("r3", "r2", "r1")


@pytest.mark.parametrize(
    "targets",
    [
        (CUBE, PLA, grams("min_mass", 50)),
        (CUBE, {"kind": "made_of", "material": "asa"}),
        ({"kind": "made_of", "material": "asa"}, grams("min_mass", 50)),
    ],
    ids=["known density", "no mass bound", "no volume bound"],
)
def test_nothing_is_said_when_the_density_is_known_or_not_needed(
    targets: tuple[dict[str, Any], ...],
) -> None:
    assert unweighed(brief(*targets), TABLE) is None
