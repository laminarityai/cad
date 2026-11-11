"""The confirmed holed plate the own-measurement tests score, and their request rows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from conftest import Person, Session

HOLED_PLATE = (
    "from build123d import *\nresult = Box(40, 20, 3) - Pos(10, 0, 0) * Cylinder(2.1, 3)\n"
)
TEXT = "A mounting plate under 150 g. It bolts on with M4 screws. It looks tidy."
ROWS: list[dict[str, Any]] = [
    {
        "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
        "quote": "under 150 g",
    },
    {
        "target": {"kind": "unchecked", "statement": "The holes fit M4 screws"},
        "quote": "It bolts on with M4 screws",
    },
    {
        "target": {"kind": "unchecked", "statement": "The plate looks tidy"},
        "quote": "It looks tidy",
    },
]
HOLE = (
    "bores = [f for f in part.faces() if f.geom_type == GeomType.CYLINDER]\n"
    "report('smallest_hole', min(2 * f.radius for f in bores), 'mm')"
)


async def confirmed(s: Session, person: Person) -> tuple[str, str, str]:
    person.answer = "confirm"
    created = await s.call("create_brief", text=TEXT)
    brief_id = created["brief_id"]
    await s.call("propose_requirements", brief_id=brief_id, requirements=ROWS)
    assert (await s.call("ask_to_confirm", project_id=created["project_id"]))["status"] == (
        "answered"
    )
    listed = await s.call("list_requirements", brief_id=brief_id)
    unchecked = next(
        r["requirement"]["id"]
        for r in listed["proposals"][0]["requirements"]
        if r["requirement"]["target"]["kind"] == "unchecked"
    )
    built = await s.call(
        "build_variant",
        code=HOLED_PLATE,
        brief_id=brief_id,
        material_key="prusament-pla",
        material_reason="PLA is light and prints easily",
    )
    variant_id = built["variant_id"]
    return brief_id, unchecked, variant_id


def own(requirement_id: str, code: str, title: str = "Smallest hole diameter") -> dict[str, str]:
    return {"requirement_id": requirement_id, "title": title, "code": code}
