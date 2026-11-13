"""What a requirement is about. A brief holds at most one requirement for each key, so a changed
number replaces the old row instead of standing beside it."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, assert_never

from cad.briefs.holes import FastenerHoles, PlainHoles
from cad.briefs.kind import Kind
from cad.briefs.model import (
    AgentLimit,
    ClosedSolid,
    Envelope,
    FitsWith,
    MadeOf,
    MaxClearance,
    MaxDeflection,
    MaxMass,
    MeasureLimit,
    MinClearance,
    MinMass,
    MinSafetyFactor,
    Target,
    Unchecked,
)

LOAD_CASE: Final = "load case"
PER: Final[Mapping[Kind, str]] = {
    Kind.ENVELOPE: "",
    Kind.MADE_OF: "",
    Kind.MAX_MASS: "",
    Kind.MIN_MASS: "",
    Kind.MIN_SAFETY_FACTOR: LOAD_CASE,
    Kind.MAX_DEFLECTION: LOAD_CASE,
    Kind.MIN_CLEARANCE: "part",
    Kind.MAX_CLEARANCE: "part",
    Kind.FITS_WITH: "part",
    Kind.MEASURE_LIMIT: "measure and comparator",
    Kind.AGENT_LIMIT: "check_sha256 and comparator",
}
"""Each kind a brief holds one of, with the subject it holds one per, empty for one per brief.
The agent's guidance is written from this table, so the rule it is told is the rule refused."""


@dataclass(frozen=True, slots=True)
class TargetKey:
    """The kind and what it is about. `per` names that subject in a refusal, empty for a kind a
    brief holds one of, and two keys that differ only in `per` are one key."""

    kind: Kind
    about: str = ""
    per: str = field(default="", compare=False)

    @property
    def rule(self) -> str:
        return f"a brief holds one {self.kind}" + (f" per {self.per}" if self.per else "")


def target_key(target: Target) -> TargetKey | None:
    """None for a target a brief may hold many of, such as two sets of holes."""
    match target:
        case MaxMass() | MinMass() | Envelope() | MadeOf():
            return TargetKey(target.kind)
        case MinSafetyFactor() | MaxDeflection():
            return TargetKey(target.kind, target.load.unit_case, PER[target.kind])
        case MinClearance() | MaxClearance() | FitsWith():
            return TargetKey(target.kind, target.part, PER[target.kind])
        case MeasureLimit():
            about = f"{target.check_id}:{target.measure}:{target.comparator}"
            return TargetKey(target.kind, about, PER[target.kind])
        case AgentLimit():
            about = f"{target.check_sha256}:{target.comparator}"
            return TargetKey(target.kind, about, PER[target.kind])
        case ClosedSolid() | Unchecked() | FastenerHoles() | PlainHoles():
            return None
        case _:
            assert_never(target)
