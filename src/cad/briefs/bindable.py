"""The team measures a person's limit may bind to, each with the words the page shows for it.

The team owns this table. A key is a check id and one of its measures, read by exact key from the
check's result, so `hole_diameter:0` is the first diameter the holes check lists, its narrowest.
Add a measure only when it keeps its value under a rotation, a translation and a
reordering of the part's faces: a bounding-box extent does not, so it stays out.
"""

from collections.abc import Mapping
from typing import Final, NamedTuple


class Bindable(NamedTuple):
    unit: str
    words: str


BINDABLE: Final[Mapping[tuple[str, str], Bindable]] = {
    ("mass", "volume"): Bindable("mm^3", "the volume of material in the part"),
    ("holes", "hole_count"): Bindable("dimensionless", "the number of round holes in the part"),
    ("holes", "hole_diameter:0"): Bindable(
        "mm", "the diameter of the narrowest round hole in the part"
    ),
    ("min_wall", "min_wall"): Bindable("mm", "the thickness of the part's thinnest wall"),
}
