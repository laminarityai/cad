"""What a requirement is about. A brief holds at most one requirement for each key, so a changed
number replaces the old row instead of standing beside it."""

from dataclasses import dataclass, field
from typing import assert_never

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
            return TargetKey(target.kind, target.load.unit_case, "load case")
        case MinClearance() | MaxClearance() | FitsWith():
            return TargetKey(target.kind, target.part, "part")
        case MeasureLimit():
            about = f"{target.check_id}:{target.measure}:{target.comparator}"
            return TargetKey(target.kind, about, "measure and comparator")
        case AgentLimit():
            about = f"{target.check_sha256}:{target.comparator}"
            return TargetKey(target.kind, about, "check and comparator")
        case ClosedSolid() | Unchecked() | FastenerHoles() | PlainHoles():
            return None
        case _:
            assert_never(target)
