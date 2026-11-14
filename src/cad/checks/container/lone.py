"""The one solid a load case acts on, taken out of the variant and solved alone (ADR-0014).

Face k of solid i is face `offset + k` of the whole result, where `offset` counts the faces of the
solids before it, so the faces a solve fixed and loaded convert to the variant's by that offset.
"""

from collections.abc import Collection
from dataclasses import dataclass, replace

from cad.checks.container.check import Subject
from cad.checks.container.kernel import Shape
from cad.checks.container.wire import FacesWire, FindingWire, MeasuredWire, WhereWire

NAME_ONE = "name one body of one solid in the load case, and the check solves that body alone"


@dataclass(frozen=True, slots=True)
class Lone:
    """`subject` holds the lone solid, a mesher of its BREP alone and its body's material."""

    subject: Subject
    shape: Shape
    offset: int
    body: str | None


def alone(subject: Subject, shape: Shape, body: str | None) -> Lone | str:
    """The solid the case acts on, or the reason there is none to solve."""
    solids = subject.kernel.solids(shape)
    if body is None:
        if len(solids) > 1:
            return (
                f"the load case names no body, and the variant has {len(solids)} solids, whose "
                f"joints no check models; {NAME_ONE}"
            )
        return Lone(subject, shape, 0, None)
    named = next((one for one in subject.bodies if one.name == body), None)
    if named is None:
        return f"the variant holds no body named {body}, so no stress was solved"
    if len(named.solids) != 1:
        return f"the body {body} has {len(named.solids)} solids; {NAME_ONE}"
    (index,) = named.solids
    solid = solids[index]
    kernel = subject.kernel
    offset = sum(len(kernel.faces(before)) for before in solids[:index])
    lone = replace(
        subject,
        shape=solid,
        fem=subject.fem.alone(kernel.brep_bytes(solid)),
        inputs=named.inputs,
        bodies=(),
    )
    return Lone(lone, solid, offset, body)


def placed(found: FindingWire, lone: Lone, echoes: Collection[str]) -> FindingWire:
    """The finding with its faces numbered as the whole variant's, its reason naming the body it
    solved, and each value it echoes named `<name>:<body>`, as the host sent it."""
    body = lone.body
    if body is None:
        return found
    measured: list[MeasuredWire] = [
        {**one, "name": f"{one['name']}:{body}"} if one["name"] in echoes else one
        for one in found["measured"]
    ]
    moved: FindingWire = {
        **found,
        "reason": f"solved the body {body} alone, in its own material: {found['reason']}",
        "measured": measured,
    }
    where = found.get("where")
    if where is not None:
        moved["where"] = _shifted(where, lone.offset)
    return moved


def _shifted(where: WhereWire, offset: int) -> WhereWire:
    moved: WhereWire = {**_faces(where, offset)}
    displacement = where.get("displacement")
    if displacement is not None:
        moved["displacement"] = _faces(displacement, offset)
    return moved


def _faces(faces: FacesWire, offset: int) -> FacesWire:
    return {
        "support": [offset + one for one in faces["support"]],
        "load": [offset + one for one in faces["load"]],
    }
