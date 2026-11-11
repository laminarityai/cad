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
    limits,
)
from cad.briefs.words import describe
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
        {"kind": "min_clearance", "part": "rail", "clearance": grams(0.2, "mm")},
        {"kind": "min_clearance", "part": "part-" + "a" * 16, "clearance": grams(0.2)},
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
    assert set(EXAMPLES) == set(Kind)
    assert {kind: deciding_check(target(raw)) for kind, raw in EXAMPLES.items()} == {
        Kind.CLOSED_SOLID: "closed_solid",
        Kind.MAX_MASS: "mass",
        Kind.MIN_MASS: "mass",
        Kind.ENVELOPE: "extents",
        Kind.MEASURE_LIMIT: "mass",
        Kind.UNCHECKED: None,
        Kind.MADE_OF: None,
        Kind.MIN_SAFETY_FACTOR: "fea",
        Kind.MAX_DEFLECTION: "fea",
        Kind.MIN_CLEARANCE: "fit",
        Kind.MAX_CLEARANCE: "fit",
        Kind.FASTENER_HOLES: "holes",
        Kind.PLAIN_HOLES: "holes",
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
        (
            {"kind": "fastener_holes", "size": "M5", "fit": "clearance", "count": 2},
            "2 holes that fit an M5 bolt",
        ),
        (
            {"kind": "fastener_holes", "size": "M4", "fit": "tapped", "count": 1},
            "1 hole tapped for M4",
        ),
        (
            {"kind": "fastener_holes", "size": "M3", "fit": "clearance"},
            "A hole that fits an M3 bolt",
        ),
        (
            {"kind": "plain_holes", "diameter": grams(8, "mm"), "count": 3},
            "3 holes of 8 mm diameter",
        ),
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
        ({"kind": "fastener_holes", "size": "M5", "fit": "tapped"}, []),
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


LOAD: dict[str, Any] = {
    "support": {"kind": "flat_end"},
    "load": {"kind": "far_end", "force": grams(10, "N"), "direction": {"kind": "any"}},
}
PART = "part-" + "a" * 16
EXAMPLES: dict[Kind, dict[str, Any]] = {
    Kind.CLOSED_SOLID: {"kind": "closed_solid"},
    Kind.MAX_MASS: {"kind": "max_mass", "mass": grams(150)},
    Kind.MIN_MASS: {"kind": "min_mass", "mass": grams(10)},
    Kind.ENVELOPE: {"kind": "envelope", "edges": [grams(1, "mm"), grams(2, "mm"), grams(3, "mm")]},
    Kind.MEASURE_LIMIT: {
        "kind": "measure_limit",
        "check_id": "mass",
        "measure": "volume",
        "comparator": "at_most",
        "limit": grams(30, "cm^3"),
    },
    Kind.UNCHECKED: {"kind": "unchecked", "statement": "holds a shelf"},
    Kind.MADE_OF: {"kind": "made_of", "material": "prusament-pla"},
    Kind.MIN_SAFETY_FACTOR: {"kind": "min_safety_factor", "load": LOAD, "factor": 2},
    Kind.MAX_DEFLECTION: {"kind": "max_deflection", "load": LOAD, "deflection": grams(2, "mm")},
    Kind.MIN_CLEARANCE: {"kind": "min_clearance", "part": PART, "clearance": grams(0.2, "mm")},
    Kind.MAX_CLEARANCE: {"kind": "max_clearance", "part": PART, "clearance": grams(0.5, "mm")},
    Kind.FASTENER_HOLES: {"kind": "fastener_holes", "size": "M5", "fit": "clearance", "count": 2},
    Kind.PLAIN_HOLES: {"kind": "plain_holes", "diameter": grams(8, "mm")},
}


def test_every_deciding_check_and_every_limit_names_a_registered_check_and_its_measure() -> None:
    measures = {spec.id: spec.measures for spec in SPECS}
    assert set(EXAMPLES) == set(Kind)
    for kind, raw in EXAMPLES.items():
        check_id = deciding_check(target(raw))
        held: tuple[Limit, ...] = limits(target(raw))
        if check_id is None:
            assert held == ()
            continue
        assert check_id in measures, f"{kind} is decided by {check_id}, which is not registered"
        for one in held:
            base, _, part = one.measure.partition(":")
            assert base in measures[check_id], f"{check_id} declares no measure {base!r}"
            assert not part or part in extents.SORTED_NAMES, f"{one.measure} is never measured"


@pytest.mark.parametrize(
    "raw",
    [
        {"kind": "fastener_holes", "size": "M7", "fit": "clearance"},
        {"kind": "fastener_holes", "size": "m5", "fit": "clearance"},
        {"kind": "fastener_holes", "size": "M5", "fit": "loose"},
        {"kind": "fastener_holes", "size": "M5", "fit": "tapped", "count": 0},
        {"kind": "plain_holes", "diameter": grams(0, "mm")},
        {"kind": "plain_holes", "diameter": grams(8, "g")},
        {"kind": "plain_holes", "diameter": grams(8, "mm"), "count": 1.5},
    ],
)
def test_a_holes_target_names_a_table_size_a_fit_and_a_whole_count(raw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        target(raw)


@pytest.mark.parametrize("key", ["Bambu PLA Basic", "bambu_pla", "", "-pla", "pla-"])
def test_a_made_of_key_must_have_the_shape_of_a_table_key(key: str) -> None:
    with pytest.raises(ValidationError):
        target({"kind": "made_of", "material": key})
