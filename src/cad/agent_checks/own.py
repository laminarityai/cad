"""The agent's own measurements on a scored variant: an agent-written check with no limit, which
runs through the same harness and never gets a verdict (ADR-0011, ADR-0008)."""

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Final

from pydantic import Field

from cad.agent_checks import harness
from cad.agent_checks.harness import Brep, Failed, Slot
from cad.agent_checks.model import MAX_CODE_CHARS, UNITS
from cad.briefs.model import Unchecked
from cad.briefs.store import ConfirmedSet
from cad.errors import Refused
from cad.frozen import Frozen
from cad.sandbox import image
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard.model import AgentMeasurement, AgentValue, Scorecard
from cad.tables.materials import UNITS as PINT
from cad.variants import entry

MAX_SNIPPETS: Final = 4


class OwnMeasurementRequest(Frozen):
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
        brep = entry.open_entry(root, variant_id, image.image_tag(image.BUILD)).brep
        ran = harness.run([Brep(brep)], [Slot(one.code, 0) for one in requested])
    except (SandboxUnavailable, entry.VariantRefused) as error:
        return tuple(
            _row(one, failed=f"the sandbox could not run it: {error}") for one in requested
        )
    rows: list[AgentMeasurement] = []
    for one, outcome in zip(requested, ran, strict=True):
        if isinstance(outcome, Failed):
            rows.append(_row(one, failed=outcome.reason))
            continue
        values = tuple(
            AgentValue(name=r.name, value=PINT.Quantity(r.value, UNITS[r.unit]))
            for r in outcome.readings
        )
        dropped = outcome.dropped
        note = (
            f"{dropped} more values were dropped: at most {harness.MAX_VALUES} are kept"
            if dropped > 0
            else None
        )
        rows.append(_row(one, values=values, note=note))
    return tuple(rows)


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
