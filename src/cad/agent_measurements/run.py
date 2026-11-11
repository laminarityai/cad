"""Run the agent's own measuring code on a scored variant, as information that never grades.

`cad.scorecard.score` must never import this module: check versions hash what it imports, and
this code can change without moving a team check version.
"""

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Final, cast

from pydantic import BaseModel, ConfigDict, Field

from cad.agent_measurements.script import MARK, compose
from cad.briefs.model import Unchecked
from cad.briefs.store import ConfirmedSet
from cad.errors import Refused
from cad.sandbox import host, image
from cad.sandbox.outcome import (
    BuildFailed,
    Failure,
    NoResult,
    OutOfMemory,
    SandboxUnavailable,
    TimedOut,
)
from cad.scorecard.model import AgentMeasurement, AgentValue, Scorecard
from cad.tables.materials import UNITS
from cad.variants import entry

MAX_SNIPPETS: Final = 4
MAX_CODE_CHARS: Final = 16 * 1024
MAX_VALUES: Final = 8
WALL_SECONDS: Final = 30
MAX_BREP_BYTES: Final = 32 * 2**20
NAME: Final = re.compile(r"[a-z][a-z0-9_]{0,31}")
UNIT_NAMES: Final[Mapping[str, str]] = {
    "mm": "mm",
    "mm^2": "mm**2",
    "mm^3": "mm**3",
    "deg": "degree",
    "1": "dimensionless",
}
TOO_LARGE: Final = "part too large to measure here"
CUT: Final = "not reported: its output was lost or cut to the last 8 KiB"


class OwnMeasurementRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str
    title: Annotated[str, Field(min_length=1, max_length=80)]
    code: Annotated[str, Field(min_length=1, max_length=MAX_CODE_CHARS)]


type OwnMeasurements = Annotated[list[OwnMeasurementRequest], Field(max_length=MAX_SNIPPETS)]


class MeasurementRefused(Refused):
    pass


def refuse_unless_unchecked(
    confirmed: ConfirmedSet | None, requested: Sequence[OwnMeasurementRequest]
) -> None:
    """Refuse before anything runs unless each request names a distinct unchecked requirement
    of the confirmed brief."""
    if confirmed is None:
        raise MeasurementRefused(
            "own_measurements needs a brief_id whose requirements the user confirmed. "
            "Nothing was scored."
        )
    unchecked = {r.id for r in confirmed.requirements if isinstance(r.target, Unchecked)}
    seen: set[str] = set()
    for one in requested:
        if one.requirement_id not in unchecked:
            raise MeasurementRefused(
                f"requirement {one.requirement_id!r} is not an unchecked requirement of brief "
                f"{confirmed.brief_id}: your own measurement may only describe a requirement no "
                "check covers. Nothing was scored."
            )
        if one.requirement_id in seen:
            raise MeasurementRefused(
                f"requirement {one.requirement_id!r} appears twice in own_measurements. "
                "Nothing was scored."
            )
        seen.add(one.requirement_id)


def attach[C: Scorecard](card: C, rows: Sequence[AgentMeasurement]) -> C:
    return type(card).model_validate({**dict(card), "not_verified": tuple(rows)})


def measure(
    root: Path, variant_id: str, requested: Sequence[OwnMeasurementRequest]
) -> tuple[AgentMeasurement, ...]:
    """Never raises for a sandbox failure: the rows say what went wrong, and the team card
    stands as the checks produced it."""
    try:
        tag = image.image_tag(image.BUILD)
        brep = entry.open_entry(root, variant_id, tag).brep
        if len(brep) > MAX_BREP_BYTES:
            return tuple(_row(one, failed=TOO_LARGE) for one in requested)
        script = compose(brep, [one.code for one in requested], MAX_VALUES)
        ran = host.build(script, image.current_image(tag), wall_seconds=WALL_SECONDS)
    except (SandboxUnavailable, entry.VariantRefused) as error:
        return tuple(
            _row(one, failed=f"the sandbox could not run it: {error}") for one in requested
        )
    slots = _slots(ran.output)
    unfinished = _unfinished(ran.verdict)
    return tuple(
        _judged_row(one, slots.get(slot, _Slot()), unfinished) for slot, one in enumerate(requested)
    )


@dataclass
class _Slot:
    values: list[Mapping[str, object]] = field(default_factory=list[Mapping[str, object]])
    failed: str | None = None
    done: bool = False
    sent: int = 0
    dropped: int = 0


def _slots(output: str) -> dict[int, _Slot]:
    slots: dict[int, _Slot] = {}
    for line in output.splitlines():
        if not line.startswith(MARK):
            continue
        try:
            raw = json.loads(line[len(MARK) :])
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        fields = cast(Mapping[str, object], raw)
        slot = fields.get("slot")
        if not isinstance(slot, int) or isinstance(slot, bool):
            continue
        held = slots.setdefault(slot, _Slot())
        if "failed" in fields:
            held.failed = str(fields["failed"])[:300]
        elif fields.get("done") is True:
            held.done = True
            held.sent, held.dropped = _count(fields, "sent"), _count(fields, "dropped")
        else:
            held.values.append(fields)
    return slots


def _count(fields: Mapping[str, object], key: str) -> int:
    count = fields.get(key)
    return count if isinstance(count, int) and not isinstance(count, bool) else -1


def _unfinished(verdict: host.Artifacts | Failure) -> str:
    match verdict:
        case TimedOut(limit_seconds=seconds):
            return f"timed out after {seconds} s"
        case OutOfMemory():
            return "ran out of memory"
        case BuildFailed(error=error):
            return f"not reported: the measuring run failed: {error[:300]}"
        case NoResult() | host.Artifacts():
            return CUT


def _judged_row(one: OwnMeasurementRequest, slot: _Slot, unfinished: str) -> AgentMeasurement:
    if slot.failed is not None:
        return _row(one, failed=slot.failed)
    if not slot.done:
        return _row(one, failed=unfinished)
    if len(slot.values) != slot.sent:
        return _row(one, failed=CUT)
    if not slot.values:
        return _row(one, failed="the code reported no value")
    values: list[AgentValue] = []
    for raw in slot.values:
        parsed = _value(raw)
        if isinstance(parsed, str):
            return _row(one, failed=parsed)
        if any(kept.name == parsed.name for kept in values):
            return _row(one, failed=f"value name {parsed.name} was reported twice")
        values.append(parsed)
    note = (
        f"{slot.dropped} more values were dropped: at most {MAX_VALUES} are kept"
        if slot.dropped > 0
        else None
    )
    return _row(one, values=tuple(values), note=note)


def _value(raw: Mapping[str, object]) -> AgentValue | str:
    name, value, unit = raw.get("name"), raw.get("value"), raw.get("unit")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return f"value name {name!r} does not match {NAME.pattern}"
    if not isinstance(value, float) or not math.isfinite(value):
        return f"value {name} is {value!r}, not a finite number"
    if not isinstance(unit, str) or unit not in UNIT_NAMES:
        return f"value {name} has unit {unit!r}, not one of {', '.join(UNIT_NAMES)}"
    return AgentValue(name=name, value=UNITS.Quantity(value, UNIT_NAMES[unit]))


def _row(
    one: OwnMeasurementRequest,
    *,
    values: tuple[AgentValue, ...] = (),
    failed: str | None = None,
    note: str | None = None,
) -> AgentMeasurement:
    return AgentMeasurement(
        requirement_id=one.requirement_id,
        title=one.title,
        code_sha256=hashlib.sha256(one.code.encode("utf-8", "surrogatepass")).hexdigest(),
        code=one.code,
        values=values,
        failed=failed,
        note=note,
    )
