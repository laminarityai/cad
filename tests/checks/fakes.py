from dataclasses import dataclass, field

from cad.checks.container.inputs import Input
from cad.checks.container.kernel import EdgeUses, Shape, StepTooLarge, Unreadable, VolumeProps
from cad.checks.container.suite import CHECKS
from cad.checks.container.wire import RequestWire, ValueKnown, ValueWire

KNOWN: ValueKnown = {"kind": "known", "magnitude": 1.24e-6}
UNREADABLE_BREP = b"unreadable"
REPORT_CAP = 64 * 2**20


@dataclass(frozen=True, slots=True)
class FakeShape:
    index: int = 0

    def IsNull(self) -> bool:
        return False


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

    def read_brep(self, data: bytes) -> Shape | Unreadable:
        return Unreadable("not a BREP") if data == UNREADABLE_BREP else FakeShape()

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

    def extents(self, shape: Shape) -> tuple[float, float, float] | None:
        return self.box

    def common_volume(self, first: Shape, second: Shape) -> float | None:
        assert isinstance(first, FakeShape) and isinstance(second, FakeShape)
        return self.commons.get((first.index, second.index), 0.0)

    def step_bytes(self, shape: Shape, cap: int) -> bytes | StepTooLarge:
        if self.step_raises:
            raise RuntimeError("no STEP")
        return StepTooLarge(len(self.step)) if len(self.step) > cap else self.step


def request(density: ValueWire = KNOWN, checks: tuple[str, ...] | None = None) -> RequestWire:
    ids = [check.ID for check in CHECKS] if checks is None else list(checks)
    return {"checks": ids, "values": {Input.DENSITY: density}}
