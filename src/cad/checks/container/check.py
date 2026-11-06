"""What a check module looks like. A check is one file: constants that describe it, and `run`.

The check version is the hash of that file plus the shared files beside it (see
`cad.checks.report`), so everything that decides a verdict, including FORMULA and SOURCES, is
inside what the version covers.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from cad.checks.container.kernel import Kernel, Shape, Unreadable
from cad.checks.container.wire import DensityWire, FindingWire, MeasuredWire, SourceLiteral

DIMENSIONLESS = "dimensionless"


@dataclass(frozen=True, slots=True)
class Subject:
    """Everything a check may read: the kernel, the parsed shape (or why there is none), and the
    density the host looked up by exact key. A check reads nothing else."""

    kernel: Kernel
    shape: Shape | Unreadable
    density: DensityWire


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

    def run(self, subject: Subject) -> FindingWire: ...


def measure(name: str, magnitude: float, unit: str) -> MeasuredWire:
    return {"name": name, "magnitude": float(magnitude), "unit": unit}


def finding(
    verdict: Literal["pass", "fail", "unknown"], reason: str, *measured: MeasuredWire
) -> FindingWire:
    """A number that is not finite cannot be reported, so it turns any verdict into `unknown`."""
    broken = [one["name"] for one in measured if not math.isfinite(one["magnitude"])]
    if broken:
        return {
            "verdict": "unknown",
            "measured": [],
            "reason": f"{reason}; not a finite number: {', '.join(broken)}",
        }
    return {"verdict": verdict, "measured": list(measured), "reason": reason}


def no_shape(why: Unreadable) -> FindingWire:
    """The answer of every check that needs a shape when there is none: `unknown`, never `pass`.
    Only `closed_solid` turns an unreadable BREP into `fail`."""
    return finding("unknown", f"no shape to measure: {why.reason}")
