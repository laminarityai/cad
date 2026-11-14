"""Each body of a variant as one shape with its name, for the 3MF, which holds one named object
for each shape it is given."""

import importlib
from collections.abc import Sequence
from typing import Protocol, cast

from cad.sandbox.wire import AreaReport, BodyReport


class _Solid(Protocol):
    pass


class _Whole(Protocol):
    def solids(self) -> Sequence[_Solid]: ...


class _Build123d(Protocol):
    def Color(self, red: float, green: float, blue: float) -> object: ...
    def Compound(self, solids: Sequence[_Solid], *, label: str, color: object | None) -> object: ...


def of(shape: object, areas: list[AreaReport], bodies: list[BodyReport]) -> list[object] | None:
    """One compound per body, named, and coloured as the area of its name is. None for no bodies,
    or when the bodies name a solid the shape does not have."""
    solids = cast(_Whole, shape).solids()
    if not bodies or len(solids) != sum(len(body["solids"]) for body in bodies):
        return None
    build123d = cast(_Build123d, importlib.import_module("build123d"))
    painted = {area["name"]: area["colour"] for area in reversed(areas)}
    return [
        build123d.Compound(
            [solids[solid] for solid in body["solids"]],
            label=body["name"],
            color=_colour(build123d, painted.get(body["name"])),
        )
        for body in bodies
    ]


def _colour(build123d: _Build123d, hex_colour: str | None) -> object | None:
    if hex_colour is None:
        return None
    red, green, blue = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return build123d.Color(red, green, blue)
