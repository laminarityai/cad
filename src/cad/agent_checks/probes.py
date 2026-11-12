"""G4, repeat and turn, before any variant exists (ADR-0011).

The geometry code runs on four team probe shapes and the agent's own probe, in two containers,
the second with each shape turned and moved. The probes are public and the motion sits in the
script the code runs beside, so code written to fool this gate can. It stops honest mistakes: a
bounding box, a random number, hash order, a hard-coded answer. On a scored variant a team-only
container makes the turn, and that run decides.
"""

import math
from collections.abc import Mapping
from typing import Final

from cad.agent_checks import harness
from cad.agent_checks.formula import Dimension, dimension_of
from cad.agent_checks.gates import Shaped
from cad.agent_checks.harness import Motion, Probe, Slot
from cad.agent_checks.model import UNITS, CheckDraft, GeometryInput
from cad.agent_checks.turned import Measured, Unmeasured, Unsound, agree

# No two probes share a thickness, a length or a width, so an honest length differs across them.
TEAM_PROBES: Final[Mapping[str, str]] = {
    "the box probe": "probe = Box(40, 30, 20)",
    "the holed plate probe": "probe = Box(60, 40, 3) - Cylinder(4, 3)",
    "the L-bracket probe": (
        "probe = Box(50, 25, 4, align=Align.MIN) + Box(4, 25, 30, align=Align.MIN)"
    ),
    "the open tray probe": "probe = Box(50, 40, 30) - Pos(0, 0, 2) * Box(46, 36, 30)",
}
SAME: Final = 1e-9


def repeat_and_turn(draft: CheckDraft, shaped: Shaped) -> str | None:
    """Why the geometry code is refused, or None. Raises SandboxUnavailable."""
    if draft.geometry is None:
        return None
    named = {**TEAM_PROBES, **({"your probe": draft.probe} if draft.probe else {})}
    shapes = [Probe(code) for code in named.values()]
    slots = [Slot(draft.geometry, number) for number in range(len(shapes))]
    plain = harness.run(shapes, slots)
    turned = harness.run(shapes, slots, Motion.drawn())
    wanted = {
        one.name: dimension_of(UNITS[draft.example.inputs[one.name].unit])
        for one in shaped.bound
        if isinstance(one.binding, GeometryInput)
    }
    measured: dict[str, Measured] = {}
    unmeasured: list[str] = []
    for probe, one, two in zip(named, plain, turned, strict=True):
        match agree(one, two, wanted):
            case Unsound(reason=reason):
                return f"on {probe}, {reason}"
            case Unmeasured(reason=reason):
                unmeasured.append(f"on {probe}, {reason}")
            case found:
                measured[probe] = found
    if not measured:
        return f"the geometry code gave no values on any probe shape: {'; '.join(unmeasured)}"
    return _constant(measured, wanted)


def _constant(measured: Mapping[str, Measured], wanted: Mapping[str, Dimension]) -> str | None:
    """A length that is the same on every probe the code measured is not read from the part."""
    if len(measured) < 2:
        return None
    for name, dimension in wanted.items():
        if dimension != dimension_of("mm"):
            continue
        found = [float(one[name].m_as("mm")) for one in measured.values()]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        if all(math.isclose(value, found[0], rel_tol=SAME, abs_tol=SAME) for value in found):
            return (
                f"the geometry code gave {name} = {found[0]:g} mm on each of "
                f"{', '.join(measured)}: a measure of the part changes with the part"
            )
    return None
