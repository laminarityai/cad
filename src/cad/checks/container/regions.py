from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from cad.checks.container.vectors import Point, dot, sub

FAR_FRACTION: Final = 0.005


@dataclass(frozen=True, slots=True)
class Bore:
    """The cylinder at `radius` around origin + t * axis, for t from t0 to t1."""

    origin: Point
    axis: Point
    radius: float
    t0: float
    t1: float


@dataclass(frozen=True, slots=True)
class Plane:
    point: Point
    normal: Point
    """Unit, pointing out of the material."""


@dataclass(frozen=True, slots=True)
class Disc:
    """The part of the plane through `center` with this normal within `radius` of `center`."""

    center: Point
    normal: Point
    radius: float


type Patch = Bore | Plane | Disc


@dataclass(frozen=True, slots=True)
class Region:
    patches: tuple[Patch, ...]
    centroid: Point
    """The area-weighted centroid of the faces the anchor selected."""
    faces: frozenset[int] = frozenset()
    """The selected faces' indices in the kernel's explorer order."""


@dataclass(frozen=True, slots=True)
class FarFrom:
    center: Point
    axis: Point
    """Unit, from the support toward the part's centre of mass."""

    def reach(self, point: Point) -> float:
        return dot(sub(point, self.center), self.axis)

    def cutoff(self, surface: Sequence[Point]) -> float:
        return (1 - FAR_FRACTION) * max(self.reach(point) for point in surface)


@dataclass(frozen=True, slots=True)
class Candidate:
    support: Region
    load: Region | FarFrom
    basis: tuple[Point, ...]
    """An orthonormal basis of the directions the load may take."""


@dataclass(frozen=True, slots=True)
class Resolved:
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True, slots=True)
class Unresolved:
    reason: str
