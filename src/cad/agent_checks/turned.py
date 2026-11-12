"""Repeat and turn (ADR-0011). Agent geometry code runs in two containers, once on the shape as
stored and once on it turned and moved by a rigid motion the agent cannot compute. A value used
in a formula is one both runs gave and agreed on.

On a scored variant a team-only container turns the part first, so no container that runs agent
code ever holds the motion.
"""

import base64
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pint

from cad.agent_checks import harness
from cad.agent_checks.formula import Dimension, dimension_of
from cad.agent_checks.harness import Brep, Failed, Motion, Outcome, Slot
from cad.agent_checks.model import UNITS, AgentCheck, GeometryInput
from cad.sandbox import host, image
from cad.sandbox.outcome import BuildFailed, NoResult, OutOfMemory, TimedOut
from cad.tables.materials import UNITS as PINT

RELATIVE: Final = 1e-6
ABSOLUTE: Final = 1e-9
TURN_SECONDS: Final = 60
TURN: Final = """
import base64
from build123d import *
with open("/tmp/part.brep", "wb") as file:
    file.write(base64.b64decode({brep!r}))
result = import_brep("/tmp/part.brep").rotate(
    Axis((0, 0, 0), {axis!r}), {degrees!r}, transform=True
).translate({offset!r}, transform=True)
"""

type Measured = Mapping[str, pint.Quantity]


@dataclass(frozen=True, slots=True)
class Unmeasured:
    """The code gave no usable values on this shape."""

    reason: str


@dataclass(frozen=True, slots=True)
class Unsound:
    """The code's values cannot be trusted: they changed between runs, came from one run only,
    or are not in the dimension the formula reads."""

    reason: str


def on_variant(
    brep: bytes, checks: Sequence[AgentCheck]
) -> tuple[Measured | Unmeasured | Unsound, ...]:
    """The geometry inputs of each check, in order: each check must hold geometry code. Raises
    SandboxUnavailable."""
    slots = [Slot(check.geometry or "", 0) for check in checks]
    plain = harness.run([Brep(brep)], slots)
    turned = turn(brep, Motion.drawn())
    if isinstance(turned, str):
        return tuple(
            Unmeasured(f"the part could not be turned and moved: {turned}") for _ in checks
        )
    moved = harness.run([Brep(turned)], slots)
    return tuple(
        agree(one, two, geometry_dimensions(check))
        for one, two, check in zip(plain, moved, checks, strict=True)
    )


def turn(brep: bytes, motion: Motion) -> bytes | str:
    """The part turned and moved by `motion`, baked into its geometry, by team code alone."""
    if len(brep) > harness.MAX_BREP_BYTES:
        return harness.TOO_LARGE
    code = TURN.format(
        brep=base64.b64encode(brep).decode(),
        axis=motion.axis,
        degrees=motion.degrees,
        offset=motion.offset,
    )
    tag = image.image_tag(image.BUILD)
    ran = host.build(code, image.current_image(tag), wall_seconds=TURN_SECONDS)
    match ran.verdict:
        case host.Artifacts(brep=turned):
            return turned
        case TimedOut(limit_seconds=seconds):
            return f"timed out after {seconds} s"
        case OutOfMemory():
            return "ran out of memory"
        case BuildFailed(error=error):
            return error[:300]
        case NoResult():
            return "it gave no shape"


def geometry_dimensions(check: AgentCheck) -> Mapping[str, Dimension]:
    geometry = {one.name for one in check.inputs if isinstance(one.binding, GeometryInput)}
    return {
        one.name: dimension_of(UNITS[one.unit])
        for one in check.example.inputs
        if one.name in geometry
    }


def agree(
    plain: Outcome, turned: Outcome, wanted: Mapping[str, Dimension]
) -> Measured | Unmeasured | Unsound:
    match plain, turned:
        case Failed(reason=reason), Failed():
            return Unmeasured(reason)
        case Failed(reason=reason), _:
            return Unsound(f"it failed on the part as stored ({reason}) but not turned and moved")
        case _, Failed(reason=reason):
            return Unsound(f"it failed on the part turned and moved ({reason}) but not as stored")
        case harness.Values(readings=first), harness.Values(readings=second):
            pass
    one = {r.name: PINT.Quantity(r.value, UNITS[r.unit]) for r in first}
    two = {r.name: PINT.Quantity(r.value, UNITS[r.unit]) for r in second}
    if set(one) != set(wanted) or set(two) != set(wanted):
        return Unmeasured(
            f"it reported {', '.join(sorted(one)) or 'nothing'}, but the formula reads "
            f"{', '.join(sorted(wanted))}"
        )
    for name, dimension in wanted.items():
        if one[name].dimensionality != dimension or two[name].dimensionality != dimension:
            return Unsound(f"{name} is in {one[name].units:~}, not a unit the formula reads")
        a, b = _magnitude(one[name], one[name]), _magnitude(two[name], one[name])
        if not math.isclose(a, b, rel_tol=RELATIVE, abs_tol=ABSOLUTE):
            return Unsound(
                f"it gave different answers when the part was turned and moved: {name} was "
                f"{a:.6g} and then {b:.6g} {one[name].units:~}"
            )
    return one


def _magnitude(value: pint.Quantity, like: pint.Quantity) -> float:
    return float(value.m_as(like.units))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
