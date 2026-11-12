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
class Arc:
    """A circular edge: `sweep` radians of the circle at `radius` around `center` and `axis`.
    The axis may point either way."""

    center: Point
    axis: Point
    radius: float
    sweep: float


@dataclass(frozen=True, slots=True)
class Opening:
    """The inner boundary of a flat face where the material is missing, as the mouth of a hole,
    a slot or a pocket is. `edges` holds one entry per edge: an `Arc` for a circular edge and
    None for any other."""

    edges: tuple[Arc | None, ...]


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


@dataclass(frozen=True, slots=True)
class Across:
    """The ray went into the material and came out through a face that looks back at the start
    within 60 degrees: `length` is the wall's thickness at the start point."""

    length: float


@dataclass(frozen=True, slots=True)
class Glancing:
    """The ray came out through a face turned more than 60 degrees from the start face, as it does
    near a corner. That is not across a wall, so there is no reading."""


@dataclass(frozen=True, slots=True)
class Lost:
    """The kernel could not follow the ray, or the ray never came out of the material."""

    reason: str


type Reading = Across | Glancing | Lost


@dataclass(frozen=True, slots=True)
class Patch:
    """A face's parameter box, and its length in mm along u and along v: the longest of three
    lines across the box at a quarter, a half and three quarters of the other parameter."""

    u0: float
    u1: float
    v0: float
    v1: float
    length_u: float
    length_v: float


class Walls(Protocol):
    """One solid's faces, by index, ready to measure wall thickness on."""

    @property
    def patches(self) -> tuple[Patch, ...]: ...

    def reading(self, face: int, u: float, v: float) -> Reading | None:
        """From the face's point at (u, v), along the inward normal, to where the ray first comes
        out of the material. None when (u, v) is not on the face, or the normal is undefined."""
        ...


@dataclass(frozen=True, slots=True)
class StepRead:
    shape: Shape
    names: tuple[str, ...]
    """Distinct product and part names from the file, in file order, without the placeholder
    names a STEP writer fills in when nobody named the product."""


@dataclass(frozen=True, slots=True)
class Kept:
    """What `keep_solids` made of a file's shape. `solids` is a compound of the solids kept, or
    None when none was. `bodies` counts the solids and free shells the shape held, `unreadable`
    those dropped, and `loose` the faces, edges and vertices that belonged to no shell."""

    solids: Shape | None
    bodies: int
    unreadable: int
    loose: int


class Kernel(Protocol):
    def read_brep(self, data: bytes) -> Shape | Unreadable:
        """Never raises. Random bytes, an empty file and a null shape are all `Unreadable`."""
        ...

    def read_step(self, data: bytes) -> StepRead | Unreadable:
        """Reads every product of the file into one shape, in millimetres whatever unit the file
        declares. Never raises."""
        ...

    def read_stl(self, data: bytes, scale: float) -> Shape | Unreadable:
        """Binary or ASCII STL as a compound of the solids made from its closed shells, with any
        open shell and loose face kept beside them, every coordinate multiplied by `scale`.
        Never raises."""
        ...

    def keep_solids(self, shape: Shape) -> Kept:
        """Caps tolerances at 1e-3 mm (floor 1e-7), then keeps each solid that passes
        BRepCheck_Analyzer and has a positive volume. A solid turned inside out is turned back
        first."""
        ...

    def brep_bytes(self, shape: Shape) -> bytes:
        """The shape as BREP bytes that `read_brep` reads back."""
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

    def openings(self, shape: Shape) -> tuple[Opening, ...]:
        """Each inner wire of each flat face whose walls run into the material. A wire whose walls
        stand out of the face, as a boss's base does, is not an opening. A hole in a face that is
        not flat is not found."""
        ...

    def inertia(self, shape: Shape) -> Inertia: ...

    def common_volume(self, first: Shape, second: Shape) -> float | None: ...

    def min_distance(self, first: Shape, second: Shape) -> float | None:
        """BRepExtrema_DistShapeShape's minimum, or None when it is not done. On the pinned OCP a
        solid nested inside another gives 0.0, so fit decides overlap with common_volume first."""
        ...

    def walls(self, shape: Shape) -> Walls: ...

    def step_bytes(self, shape: Shape, cap: int) -> bytes | StepTooLarge:
        """The writer numbers PRODUCT names per process, so a second call raises: one
        container writes one STEP, which keeps the bytes stable."""
        ...


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "no message")
