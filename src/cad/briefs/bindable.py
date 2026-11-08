"""The team measures a person's limit may bind to, each with the words the page shows for it.

The team owns this table. A key is a check id and one of its measures, read by exact key from the
check's result. Add a measure only when it keeps its value under a rotation, a translation and a
reordering of the part's faces: a bounding-box extent does not, so it stays out.
"""

from collections.abc import Mapping
from typing import Final, NamedTuple


class Bindable(NamedTuple):
    unit: str
    words: str


BINDABLE: Final[Mapping[tuple[str, str], Bindable]] = {
    ("mass", "volume"): Bindable("mm^3", "the volume of material in the part"),
}
