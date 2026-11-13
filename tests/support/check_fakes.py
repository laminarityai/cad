from collections.abc import Sequence
from dataclasses import dataclass, field

from cad.checks.container import runner
from cad.checks.container.calculix import Material, NodalField, NodalLoads, SolveFailed
from cad.checks.container.check import Quick
from cad.checks.container.inputs import Input
from cad.checks.container.kernel import (
    Across,
    EdgeUses,
    FaceInfo,
    Inertia,
    Kept,
    Kernel,
    Opening,
    Patch,
    Point,
    Reading,
    Shape,
    StepRead,
    StepTooLarge,
    Unreadable,
    VolumeProps,
)
from cad.checks.container.mesher import MeshFailed, TetMesh
from cad.checks.container.suite import CHECKS
from cad.checks.container.wire import CheckedReport, RequestWire, StepWire, ValueKnown, ValueWire

KNOWN: ValueKnown = {"kind": "known", "magnitude": 1.24e-6}
UNREADABLE_BREP = b"unreadable"
REPORT_CAP = 64 * 2**20
TWO_MM = Across(2.0)


@dataclass(frozen=True, slots=True)
class FakeShape:
    index: int = 0

    def IsNull(self) -> bool:
        return False


class NoFem:
    def mesh(self, size_mm: float, floor_mm: float) -> TetMesh | MeshFailed:
        raise NotImplementedError("this test meshes nothing")

    def solve(
        self,
        mesh: TetMesh,
        material: Material,
        fixed: frozenset[int],
        unit_loads: Sequence[NodalLoads],
    ) -> tuple[NodalField, ...] | SolveFailed:
        raise NotImplementedError("this test solves nothing")


@dataclass(frozen=True, slots=True)
class FakeWalls:
    """`count` square faces 10 mm a side, where every ray reads `found`."""

    found: Reading | None = TWO_MM
    count: int = 1

    @property
    def patches(self) -> tuple[Patch, ...]:
        return (Patch(0.0, 1.0, 0.0, 1.0, 10.0, 10.0),) * self.count

    def reading(self, face: int, u: float, v: float) -> Reading | None:
        return self.found


@dataclass(slots=True)
class FakeKernel:
    solid_count: int = 1
    valid: bool = True
    uses: EdgeUses = field(default_factory=lambda: EdgeUses(0, 0))
    props: VolumeProps = field(default_factory=lambda: VolumeProps(1000.0, (1.0, 2.0, 3.0)))
    commons: dict[tuple[int, int], float | None] = field(
        default_factory=dict[tuple[int, int], float | None]
    )
    outside: int = 0
    box: tuple[float, float, float] | None = (30.0, 10.0, 20.0)
    invalid_raises: bool = False
    step_raises: bool = False
    step: bytes = b"STEP bytes"
    face_list: tuple[FaceInfo, ...] = ()
    mouths: tuple[Opening, ...] = ()
    wall: FakeWalls = field(default_factory=FakeWalls)

    def read_brep(self, data: bytes) -> Shape | Unreadable:
        return Unreadable("not a BREP") if data == UNREADABLE_BREP else FakeShape()

    def read_step(self, data: bytes) -> StepRead | Unreadable:
        raise NotImplementedError("no check reads a STEP file")

    def read_stl(self, data: bytes, scale: float) -> Shape | Unreadable:
        raise NotImplementedError("no check reads an STL file")

    def keep_solids(self, shape: Shape) -> Kept:
        raise NotImplementedError("no check keeps solids")

    def brep_bytes(self, shape: Shape) -> bytes:
        raise NotImplementedError("no check writes a BREP")

    def solids(self, shape: Shape) -> tuple[Shape, ...]:
        return tuple(FakeShape(index) for index in range(self.solid_count))

    def is_valid(self, shape: Shape) -> bool:
        if self.invalid_raises:
            raise RuntimeError("BRepCheck exploded\nsecond line")
        return self.valid

    def edge_uses(self, shape: Shape) -> EdgeUses:
        return self.uses

    def outside_solids(self, shape: Shape) -> int:
        return self.outside

    def volume_props(self, shape: Shape) -> VolumeProps:
        return self.props

    def bounds(self, shape: Shape) -> tuple[Point, Point] | None:
        return None if self.box is None else ((0.0, 0.0, 0.0), self.box)

    def extents(self, shape: Shape) -> tuple[float, float, float] | None:
        return self.box

    def max_tolerance(self, shape: Shape) -> float:
        return 1e-7

    def faces(self, shape: Shape) -> tuple[FaceInfo, ...]:
        return self.face_list

    def openings(self, shape: Shape) -> tuple[Opening, ...]:
        return self.mouths

    def inertia(self, shape: Shape) -> Inertia:
        return Inertia(
            volume=self.props.volume,
            center=self.props.center,
            axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            moments=(1.0, 1.0, 1.0),
            spans=((0.0, 30.0), (0.0, 10.0), (0.0, 20.0)),
        )

    def inside(self, shape: Shape, point: Point) -> bool:
        raise NotImplementedError("no quick check asks whether a point is inside")

    def reach(self, shape: Shape, direction: Point) -> float:
        raise NotImplementedError("no quick check asks how far the solid reaches")

    def common_volume(self, first: Shape, second: Shape) -> float | None:
        assert isinstance(first, FakeShape) and isinstance(second, FakeShape)
        return self.commons.get((first.index, second.index), 0.0)

    def min_distance(self, first: Shape, second: Shape) -> float | None:
        raise NotImplementedError("no quick check measures a distance")

    def walls(self, shape: Shape) -> FakeWalls:
        return self.wall

    def step_bytes(self, shape: Shape, cap: int) -> bytes | StepTooLarge:
        if self.step_raises:
            raise RuntimeError("no STEP")
        return StepTooLarge(len(self.step)) if len(self.step) > cap else self.step


def request(density: ValueWire = KNOWN, checks: tuple[str, ...] | None = None) -> RequestWire:
    quick = [check.ID for check in CHECKS if isinstance(check.BUDGET, Quick)]
    ids = quick if checks is None else list(checks)
    return {
        "checks": ids,
        "values": {Input.DENSITY: density},
        "load_cases": [],
        "context_bytes": 0,
    }


def run_report(
    wire: RequestWire, stdin: bytes, kernel: Kernel, report_cap: int = REPORT_CAP
) -> tuple[CheckedReport, StepWire]:
    """The two messages the runner sends, in the order it sends them."""
    report, step = runner.run(wire, stdin, kernel, report_cap)
    assert report["kind"] == "checked", report
    assert step["kind"] != "checked", step
    return report, step
