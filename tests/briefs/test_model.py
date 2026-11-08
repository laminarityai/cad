from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from cad.briefs.model import (
    BriefId,
    BriefSpan,
    Envelope,
    Kind,
    Limit,
    Requirement,
    RequirementId,
    Target,
    deciding_check,
    describe,
    limits,
)
from cad.checks.container import extents
from cad.checks.report import SPECS
from cad.checks.result import Comparator
from cad.tables.materials import UNITS

TARGET = TypeAdapter[Target](Target)


def target(raw: dict[str, Any]) -> Target:
    return TARGET.validate_python(raw)


def grams(magnitude: float, unit: str = "g") -> dict[str, Any]:
    return {"magnitude": magnitude, "unit": unit}


@pytest.mark.parametrize(
    "raw",
    [
        {"kind": "max_mass", "mass": grams(150, "mm")},
        {"kind": "max_mass", "mass": grams(0)},
        {"kind": "min_mass", "mass": grams(-1)},
        {"kind": "max_mass", "mass": grams(1, "furlongs per blorp")},
        {"kind": "max_mass", "mass": {"magnitude": "nan", "unit": "g"}},
        {"kind": "envelope", "edges": [grams(1, "mm"), grams(2, "mm"), grams(3, "g")]},
        {"kind": "envelope", "edges": [grams(1, "mm"), grams(2, "mm")]},
        {"kind": "closed_solid", "mass": grams(1)},
        {"kind": "unchecked", "statement": ""},
        {"kind": "unchecked", "statement": "holds a shelf", "comparator": "at_most"},
        {"kind": "max_mass", "mass": grams(1), "comparator": "at_least"},
        {"kind": "max_mass", "status": "confirmed", "mass": grams(1)},
        {"kind": "warp_drive"},
    ],
)
def test_a_target_that_does_not_fit_its_kind_is_refused(raw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        target(raw)


def test_an_envelope_is_one_target_whatever_order_its_edges_come_in() -> None:
    given = target(
        {"kind": "envelope", "edges": [grams(4, "cm"), grams(120, "mm"), grams(80, "mm")]}
    )
    reordered = target(
        {"kind": "envelope", "edges": [grams(80, "mm"), grams(4, "cm"), grams(120, "mm")]}
    )
    assert isinstance(given, Envelope)
    assert given.model_dump(mode="json") == reordered.model_dump(mode="json")
    assert [edge["magnitude"] for edge in given.model_dump(mode="json")["edges"]] == [120, 80, 4]


def test_every_kind_has_one_deciding_check_or_is_unverified() -> None:
    assert {kind: deciding_check(kind) for kind in Kind} == {
        Kind.CLOSED_SOLID: "closed_solid",
        Kind.MAX_MASS: "mass",
        Kind.MIN_MASS: "mass",
        Kind.ENVELOPE: "extents",
        Kind.UNCHECKED: None,
        Kind.MADE_OF: None,
    }


@pytest.mark.parametrize(
    ("raw", "words"),
    [
        ({"kind": "closed_solid"}, "The part is one closed solid"),
        ({"kind": "max_mass", "mass": grams(150)}, "Mass at most 150 g"),
        ({"kind": "min_mass", "mass": grams(0.2, "kg")}, "Mass at least 0.2 kg"),
        (
            {"kind": "envelope", "edges": [grams(40, "mm"), grams(120, "mm"), grams(80, "mm")]},
            "Fits inside a box of 120 mm x 80 mm x 40 mm",
        ),
        ({"kind": "unchecked", "statement": "holds a 2 kg shelf"}, "holds a 2 kg shelf"),
        ({"kind": "made_of", "material": "bambu-pla-basic"}, "Made of bambu-pla-basic"),
    ],
)
def test_a_requirement_reads_in_plain_words(raw: dict[str, Any], words: str) -> None:
    requirement = Requirement(
        id=RequirementId("0" * 16),
        brief_id=BriefId("1" * 16),
        target=target(raw),
        origin=BriefSpan(start=0, end=1),
    )
    assert describe(requirement) == words


def q(magnitude: float, unit: str) -> object:
    return UNITS.Quantity(magnitude, unit)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"kind": "closed_solid"}, []),
        ({"kind": "unchecked", "statement": "holds a shelf"}, []),
        ({"kind": "max_mass", "mass": grams(150)}, [("mass", Comparator.AT_MOST, q(150, "g"))]),
        (
            {"kind": "min_mass", "mass": grams(0.2, "kg")},
            [("mass", Comparator.AT_LEAST, q(0.2, "kg"))],
        ),
        (
            {"kind": "envelope", "edges": [grams(4, "cm"), grams(120, "mm"), grams(80, "mm")]},
            [
                ("sorted_extent:largest", Comparator.AT_MOST, q(120, "mm")),
                ("sorted_extent:middle", Comparator.AT_MOST, q(80, "mm")),
                ("sorted_extent:smallest", Comparator.AT_MOST, q(4, "cm")),
            ],
        ),
    ],
)
def test_each_kind_names_the_measures_it_is_held_to_and_the_confirmed_quantity(
    raw: dict[str, Any], expected: list[tuple[str, Comparator, object]]
) -> None:
    assert [(one.measure, one.comparator, one.quantity) for one in limits(target(raw))] == expected


EXAMPLES: dict[Kind, dict[str, Any]] = {
    Kind.CLOSED_SOLID: {"kind": "closed_solid"},
    Kind.MAX_MASS: {"kind": "max_mass", "mass": grams(150)},
    Kind.MIN_MASS: {"kind": "min_mass", "mass": grams(10)},
    Kind.ENVELOPE: {"kind": "envelope", "edges": [grams(1, "mm"), grams(2, "mm"), grams(3, "mm")]},
    Kind.UNCHECKED: {"kind": "unchecked", "statement": "holds a shelf"},
    Kind.MADE_OF: {"kind": "made_of", "material": "prusament-pla"},
}


def test_every_deciding_check_and_every_limit_names_a_registered_check_and_its_measure() -> None:
    measures = {spec.id: spec.measures for spec in SPECS}
    assert set(EXAMPLES) == set(Kind)
    for kind, raw in EXAMPLES.items():
        check_id = deciding_check(kind)
        held: tuple[Limit, ...] = limits(target(raw))
        if check_id is None:
            assert held == ()
            continue
        assert check_id in measures, f"{kind} is decided by {check_id}, which is not registered"
        for one in held:
            base, _, part = one.measure.partition(":")
            assert base in measures[check_id], f"{check_id} declares no measure {base!r}"
            assert not part or part in extents.SORTED_NAMES, f"{one.measure} is never measured"


@pytest.mark.parametrize("key", ["Bambu PLA Basic", "bambu_pla", "", "-pla", "pla-"])
def test_a_made_of_key_must_have_the_shape_of_a_table_key(key: str) -> None:
    with pytest.raises(ValidationError):
        target({"kind": "made_of", "material": key})
