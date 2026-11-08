from dataclasses import dataclass
from typing import NamedTuple, Protocol


class Shape(Protocol):
    def IsNull(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class Unreadable:
    reason: str


@dataclass(frozen=True, slots=True)
class StepTooLarge:
    size: int


class EdgeUses(NamedTuple):
    free: int
    over_used: int


class VolumeProps(NamedTuple):
    volume: float  # signed by orientation
    center: tuple[float, float, float]


class Kernel(Protocol):
    def read_brep(self, data: bytes) -> Shape | Unreadable:
        """Never raises. Random bytes, an empty file and a null shape are all `Unreadable`."""
        ...

    def solids(self, shape: Shape) -> tuple[Shape, ...]: ...

    def outside_solids(self, shape: Shape) -> int:
        """Shells, faces, edges and vertices that no solid of the shape contains."""
        ...

    def is_valid(self, shape: Shape) -> bool: ...

    def edge_uses(self, shape: Shape) -> EdgeUses:
        """A seam edge is two uses by one face and so passes. Degenerated edges
        (BRep_Tool.Degenerated_s) are skipped, because a sphere pole is used once and is not a
        hole."""
        ...

    def volume_props(self, shape: Shape) -> VolumeProps: ...

    def extents(self, shape: Shape) -> tuple[float, float, float] | None:
        """Sizes along x, y and z of the axis-aligned bounding box in the shape's own frame, or
        None when the shape has no bounds or unbounded ones. The box is the tightest the kernel
        computes (BRepBndLib.AddOptimal_s from geometry, not from the mesh, with no tolerance gap
        added)."""
        ...

    def common_volume(self, first: Shape, second: Shape) -> float | None: ...

    def step_bytes(self, shape: Shape, cap: int) -> bytes | StepTooLarge:
        """The writer numbers PRODUCT names per process, so a second call raises: one
        container writes one STEP, which keeps the bytes stable."""
        ...


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "no message")
