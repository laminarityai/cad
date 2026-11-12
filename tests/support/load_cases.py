"""Load cases written as plain dicts, the way an agent's proposal carries them."""

from typing import Any

from pydantic import TypeAdapter

from cad.loads.model import LoadCase

CASE = TypeAdapter(LoadCase)
Part = dict[str, Any]

FORCE: Part = {"magnitude": 49.0, "unit": "N"}
MM = {"magnitude": 5.5, "unit": "mm"}

SUPPORTS: dict[str, Part] = {
    "holes": {"kind": "holes", "count": 2, "diameter": MM},
    "holes_any_size": {"kind": "holes", "count": 1},
    "largest_flat": {"kind": "largest_flat"},
    "flat_end": {"kind": "flat_end"},
    "end_of_middle": {"kind": "end_of", "axis": "middle"},
    "end_of_short": {"kind": "end_of", "axis": "short"},
    "facing": {"kind": "facing"},
    "each_hole": {"kind": "each", "curve": "hole", "diameter": MM},
    "each_hole_any_size": {"kind": "each", "curve": "hole"},
    "each_inner_curve": {"kind": "each", "curve": "inner_curve"},
    "each_inner_curve_sized": {"kind": "each", "curve": "inner_curve", "diameter": MM},
    "in_one_flat_face": {"kind": "in_one_flat_face", "count": 2, "diameter": MM},
    "in_one_flat_face_any_size": {"kind": "in_one_flat_face", "count": 3},
}

LOADS: dict[str, Part] = {
    "far_end": {"kind": "far_end"},
    "on_holes": {"kind": "on_holes", "count": 1, "diameter": MM},
    "on_holes_any_size": {"kind": "on_holes", "count": 2},
    "on_largest_flat": {"kind": "on_largest_flat"},
    "on_largest_flat_middle": {"kind": "on_largest_flat", "middle": True},
    "on_opposite": {"kind": "on_opposite"},
    "on_opposite_middle": {"kind": "on_opposite", "middle": True},
    "on_farthest_hole": {"kind": "on_farthest", "curve": "hole", "diameter": MM},
    "on_farthest_hole_any_size": {"kind": "on_farthest", "curve": "hole"},
    "on_farthest_inner_curve": {"kind": "on_farthest", "curve": "inner_curve"},
    "on_farthest_inner_curve_sized": {
        "kind": "on_farthest",
        "curve": "inner_curve",
        "diameter": MM,
    },
}

DIRECTIONS: dict[str, Part] = {
    "along_long": {"kind": "along", "axis": "long"},
    "along_hole_axis": {"kind": "along", "axis": "hole_axis"},
    "across_long": {"kind": "across", "axis": "long"},
    "across_hole_axis": {"kind": "across", "axis": "hole_axis"},
    "any": {"kind": "any"},
    "into": {"kind": "into"},
    "away": {"kind": "away"},
}


def case(support: Part, load: Part, direction: Part, force: Part = FORCE) -> Part:
    return {"support": support, "load": {**load, "force": force, "direction": direction}}


def parse(support: Part, load: Part, direction: Part, force: Part = FORCE) -> LoadCase:
    return CASE.validate_python(case(support, load, direction, force))


def hole_hook() -> Part:
    """Held by 2 holes, hung from the far end across the hole axis: a reviewed phrase."""
    return case(SUPPORTS["holes"], LOADS["far_end"], DIRECTIONS["across_hole_axis"])


def shelf(force: Part = FORCE) -> Part:
    """Screwed through a flange, pressed in the middle of its largest flat face: described."""
    return case(
        SUPPORTS["in_one_flat_face"], LOADS["on_largest_flat_middle"], DIRECTIONS["into"], force
    )
