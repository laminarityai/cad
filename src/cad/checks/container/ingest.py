import math
from typing import Literal, TypedDict

from cad.checks.container.channel import serve
from cad.checks.container.kernel import Kernel, Point, Unreadable, ocp_kernel
from cad.checks.container.whole_solids import unmeasurable


class PartWire(TypedDict):
    kind: Literal["part"]
    solids: int
    volume_mm3: float
    box_min: list[float]
    box_max: list[float]


class RefusedWire(TypedDict):
    kind: Literal["refused"]
    reason: str


type IngestWire = PartWire | RefusedWire


def main() -> None:
    serve(lambda _, brep: facts(ocp_kernel(), brep))


def facts(kernel: Kernel, brep: bytes) -> IngestWire:
    shape = kernel.read_brep(brep)
    if isinstance(shape, Unreadable):
        return _refused(f"the BREP cannot be read: {shape.reason}")
    problem = unmeasurable(kernel, shape)
    if problem is not None:
        return _refused(f"the shape {problem}")
    corners = kernel.bounds(shape)
    if corners is None:
        return _refused("the shape has no bounding box")
    low, high = corners
    volume = kernel.volume_props(shape).volume
    if not all(map(math.isfinite, (volume, *low, *high))):
        return _refused("the volume or the bounding box is not a finite number")
    return {
        "kind": "part",
        "solids": len(kernel.solids(shape)),
        "volume_mm3": volume,
        "box_min": _listed(low),
        "box_max": _listed(high),
    }


def _listed(point: Point) -> list[float]:
    return [float(one) for one in point]


def _refused(reason: str) -> RefusedWire:
    return {"kind": "refused", "reason": reason}
