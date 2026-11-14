from collections.abc import Sequence
from typing import Protocol


class Solid(Protocol):
    def faces(self) -> Sequence[object]: ...


class Solids(Protocol):
    def faces(self) -> Sequence[object]: ...
    def solids(self) -> Sequence[Solid]: ...


def solid_faces(shape: Solids) -> list[int]:
    """The faces of each solid in the order the shape lists its solids. Face k of solid i is face
    `sum(counts[:i]) + k` of the whole shape, which is how its mesh numbers faces. Empty when
    the counts do not add up to the shape's faces."""
    counts = [len(solid.faces()) for solid in shape.solids()]
    return counts if sum(counts) == len(shape.faces()) else []
