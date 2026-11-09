from dataclasses import dataclass
from typing import NamedTuple, Protocol

from cad.checks.container.vectors import Point


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


@dataclass(frozen=True, slots=True)
class Flat:
    normal: Point
    """Unit, pointing out of the material."""


@dataclass(frozen=True, slots=True)
class Round:
    """A face on a circular cylinder: the points origin + v * axis at `radius` from the axis, for
    v from v0 to v1, over `span` radians around it."""

    origin: Point
    axis: Point
    radius: float
    v0: float
    v1: float
    span: float
    concave: bool
    """The face's outward normal points at the axis, so the material is outside, as in a bore."""


@dataclass(frozen=True, slots=True)
class Curved:
    pass


type Surface = Flat | Round | Curved


@dataclass(frozen=True, slots=True)
class FaceInfo:
    surface: Surface
    area: float
    centroid: Point


@dataclass(frozen=True, slots=True)
class Inertia:
    """`axes` are the solid's unit principal axes through its centroid, right-handed, and
    `moments` its principal moments of inertia about them at unit density. `spans` holds the
    lowest and highest projection of the solid on each axis, measured from the centroid."""

    volume: float
    center: Point
    axes: tuple[Point, Point, Point]
    moments: tuple[float, float, float]
    spans: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]


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

    def bounds(self, shape: Shape) -> tuple[Point, Point] | None:
        """The lowest and highest corner of the axis-aligned bounding box in the shape's own frame,
        or None when the shape has no bounds or unbounded ones. The box is the tightest the kernel
        computes (BRepBndLib.AddOptimal_s from geometry, not from the mesh, with no tolerance gap
        added)."""
        ...

    def extents(self, shape: Shape) -> tuple[float, float, float] | None:
        """Sizes along x, y and z of the `bounds` box."""
        ...

    def max_tolerance(self, shape: Shape) -> float:
        """The largest tolerance of any vertex, edge or face of the shape."""
        ...

    def faces(self, shape: Shape) -> tuple[FaceInfo, ...]:
        """Each face once, in the kernel's explorer order."""
        ...

    def inertia(self, shape: Shape) -> Inertia: ...

    def common_volume(self, first: Shape, second: Shape) -> float | None: ...

    def step_bytes(self, shape: Shape, cap: int) -> bytes | StepTooLarge:
        """The writer numbers PRODUCT names per process, so a second call raises: one
        container writes one STEP, which keeps the bytes stable."""
        ...


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "no message")
