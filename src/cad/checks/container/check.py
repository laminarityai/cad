import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from cad.checks.container.calculix import Material, NodalField, NodalLoads, SolveFailed
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.kernel import Kernel, Shape, Unreadable
from cad.checks.container.mesher import MeshFailed, TetMesh
from cad.checks.container.wire import (
    FindingWire,
    MeasuredWire,
    ResultWire,
    SourceLiteral,
    WhereWire,
)

DIMENSIONLESS = "dimensionless"


@dataclass(frozen=True, slots=True)
class Quick:
    pass


@dataclass(frozen=True, slots=True)
class Background:
    wall_seconds: int
    memory_mb: int
    tmpfs_mb: int


type Budget = Quick | Background


class Fem(Protocol):
    def mesh(self, size_mm: float, floor_mm: float) -> TetMesh | MeshFailed: ...

    def solve(
        self,
        mesh: TetMesh,
        material: Material,
        fixed: frozenset[int],
        unit_loads: Sequence[NodalLoads],
    ) -> tuple[NodalField, ...] | SolveFailed: ...


@dataclass(frozen=True, slots=True)
class Subject:
    kernel: Kernel
    fem: Fem
    shape: Shape | Unreadable
    inputs: Inputs
    reported: Mapping[str, ResultWire]
    context: Shape | Unreadable | None = None


class CheckModule(Protocol):
    """A module satisfies this by defining the names. Read-only properties let plain module
    constants match."""

    @property
    def ID(self) -> str: ...

    @property
    def FORMULA(self) -> str: ...

    @property
    def SOURCES(self) -> tuple[SourceLiteral, ...]: ...

    @property
    def MEASURES(self) -> Mapping[str, str]:
        """name -> Pint unit string. The host rejects a measured value whose unit differs."""
        ...

    @property
    def TAKES(self) -> frozenset[Input]: ...

    @property
    def READS(self) -> Mapping[str, Input]: ...

    @property
    def REQUIRES(self) -> tuple["CheckModule", ...]: ...

    @property
    def BUDGET(self) -> Budget: ...

    @property
    def ERROR_BOUNDS(self) -> Mapping[str, float]: ...

    def run(self, subject: Subject) -> FindingWire: ...


def measure(name: str, magnitude: float, unit: str) -> MeasuredWire:
    return {"name": name, "magnitude": float(magnitude), "unit": unit}


def finding(
    verdict: Literal["pass", "fail", "unknown"],
    reason: str,
    *measured: MeasuredWire,
    where: WhereWire | None = None,
) -> FindingWire:
    broken = [one["name"] for one in measured if not math.isfinite(one["magnitude"])]
    if broken:
        return {
            "verdict": "unknown",
            "measured": [],
            "reason": f"{reason}; not a finite number: {', '.join(broken)}",
        }
    found: FindingWire = {"verdict": verdict, "measured": list(measured), "reason": reason}
    if where is not None:
        found["where"] = where
    return found


def no_shape(why: Unreadable) -> FindingWire:
    return finding("unknown", f"no shape to measure: {why.reason}")


def required_pass(
    subject: Subject, requires: Sequence["CheckModule"], to: str
) -> FindingWire | None:
    for required in requires:
        found = subject.reported[required.ID]
        if found["verdict"] != "pass":
            return finding(
                "unknown",
                f"{required.ID} is {found['verdict']}, so there is no one solid to {to}: "
                f"{found['reason']}",
            )
    return None
