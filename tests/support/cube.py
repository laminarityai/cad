from typing import Any, Final

CUBE_TEXT: Final = "A block that fits in a 20 mm cube, PLA, at least 50 g"
CUBE: Final = {
    "target": {"kind": "envelope", "edges": [{"magnitude": 20, "unit": "mm"}] * 3},
    "quote": "fits in a 20 mm cube",
}
PLA: Final = {"target": {"kind": "made_of", "material": "prusament-pla"}, "quote": "PLA"}


def min_mass(grams: float) -> dict[str, Any]:
    return {
        "target": {"kind": "min_mass", "mass": {"magnitude": grams, "unit": "g"}},
        "quote": "at least 50 g",
    }
