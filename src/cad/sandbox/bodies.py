"""The bodies of a variant: which solids of its result share a name. A check measures the solids
itself from the BREP and uses a body only to learn which solid has which name. No colour, no
number and no geometry is held here."""

import hashlib
import json
import re
from typing import Annotated, Final

from pydantic import AfterValidator, Field, Strict, StringConstraints, TypeAdapter, ValidationError

from cad.frozen import Frozen

MAX_BODIES: Final = 12
# min_wall reads each body as one shape, and a quick job fits 24 solids that way, not more.
MAX_SOLIDS: Final = 24
BODY_NAME: Final = r"^[a-z][a-z0-9-]{0,31}$"
NAMED = (
    "set `label` on each body after its last shape operation, since a fuse, a fillet and "
    "`Compound([...])` drop it, and return `result = Compound(children=[...])`, or fuse what is "
    "one piece"
)
NAME_RULE = (
    "a body name starts with a lowercase letter and holds lowercase letters, digits and hyphens, "
    "up to 32 characters"
)
MAX_ECHO_CHARS: Final = 40

type BodyName = Annotated[str, Strict(), StringConstraints(pattern=BODY_NAME)]
type SolidIndex = Annotated[int, Strict(), Field(ge=0, lt=MAX_SOLIDS)]


class Body(Frozen):
    """The solids of a variant's result that share a name, numbered as the kernel's explorer
    numbers them."""

    name: BodyName
    solids: Annotated[tuple[SolidIndex, ...], Field(min_length=1)]


def _partition(bodies: tuple[Body, ...]) -> tuple[Body, ...]:
    if len({body.name for body in bodies}) != len(bodies):
        raise ValueError("two bodies share a name")
    solids = sorted(solid for body in bodies for solid in body.solids)
    if solids != list(range(len(solids))):
        raise ValueError("the bodies do not cover each solid once")
    return bodies


type Bodies = Annotated[tuple[Body, ...], Field(max_length=MAX_BODIES), AfterValidator(_partition)]
"""Empty for a result of one solid or none, which is one unnamed body."""
BODIES: Final = TypeAdapter[Bodies](Bodies)
_NAMES: Final = TypeAdapter[list[str | None]](list[str | None])


def bodies_sha256(bodies: Bodies) -> str | None:
    if not bodies:
        return None
    wire = json.dumps([body.model_dump(mode="json") for body in bodies], sort_keys=True)
    return hashlib.sha256(wire.encode()).hexdigest()


def read_bodies(raw: object) -> Bodies | str:
    """`raw` is what the runner sent from inside the sandbox: the name of each solid, None for a
    solid with no label, or the error that stopped it reading them. Returns the bodies, or why
    the build is refused."""
    unread = "the bodies of `result` could not be read: "
    if isinstance(raw, str):
        return f"{unread}{raw}"[:400]
    try:
        names = _NAMES.validate_python(raw, strict=True)
    except ValidationError:
        return f"{unread}it is not a list of names"
    if len(names) > MAX_SOLIDS:
        return (
            f"`result` has {len(names)} solids, and a variant holds at most {MAX_SOLIDS}: "
            "fuse what is one piece"
        )
    unnamed = [str(index) for index, name in enumerate(names) if name is None]
    if unnamed:
        return (
            f"{len(unnamed)} of the {len(names)} solids of `result` have no label "
            f"(solids {', '.join(unnamed)}): {NAMED}"
        )
    grouped: dict[str, list[int]] = {}
    for index, name in enumerate(names):
        grouped.setdefault(str(name), []).append(index)
    if len(grouped) > MAX_BODIES:
        return (
            f"`result` has {len(grouped)} bodies, and a variant holds at most {MAX_BODIES}: "
            "give the solids of one material one label"
        )
    bad = next((name for name in grouped if re.fullmatch(BODY_NAME, name) is None), None)
    if bad is not None:
        return f"the label {bad[:MAX_ECHO_CHARS]!r} cannot name a body: {NAME_RULE}"
    return BODIES.validate_python(
        [{"name": name, "solids": tuple(solids)} for name, solids in grouped.items()]
    )
