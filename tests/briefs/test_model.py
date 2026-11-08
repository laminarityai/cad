from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from cad.briefs.model import (
    BriefId,
    BriefSpan,
    Comparator,
    Envelope,
    Kind,
    Requirement,
    RequirementId,
    Target,
    comparator,
    deciding_check,
    describe,
)

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
    }


@pytest.mark.parametrize(
    ("raw", "expected", "words"),
    [
        ({"kind": "closed_solid"}, None, "The part is one closed solid"),
        ({"kind": "max_mass", "mass": grams(150)}, Comparator.AT_MOST, "Mass at most 150 g"),
        (
            {"kind": "min_mass", "mass": grams(0.2, "kg")},
            Comparator.AT_LEAST,
            "Mass at least 0.2 kg",
        ),
        (
            {"kind": "envelope", "edges": [grams(40, "mm"), grams(120, "mm"), grams(80, "mm")]},
            Comparator.AT_MOST,
            "Fits inside a box of 120 mm x 80 mm x 40 mm",
        ),
        ({"kind": "unchecked", "statement": "holds a 2 kg shelf"}, None, "holds a 2 kg shelf"),
    ],
)
def test_a_requirement_reads_in_plain_words_with_the_comparator_its_kind_fixes(
    raw: dict[str, Any], expected: Comparator | None, words: str
) -> None:
    parsed = target(raw)
    requirement = Requirement(
        id=RequirementId("0" * 16),
        brief_id=BriefId("1" * 16),
        target=parsed,
        origin=BriefSpan(start=0, end=1),
    )
    assert comparator(parsed) == expected
    assert describe(requirement) == words
