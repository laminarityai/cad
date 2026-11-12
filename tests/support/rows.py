from dataclasses import dataclass, field
from typing import Any

from cad.context_parts.ingest import Facts, Ingested, NotAPart, Source

TEXT = "A wall bracket for a 2 kg shelf, under 150 g, fits in 120 x 80 x 40 mm, printable in PETG"
UNDER_150 = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}
SHELF = {
    "target": {"kind": "unchecked", "statement": "holds a 2 kg shelf"},
    "quote": "for a 2 kg shelf",
}
ENVELOPE = {
    "target": {
        "kind": "envelope",
        "edges": [{"magnitude": edge, "unit": "mm"} for edge in (120, 80, 40)],
    },
    "quote": "fits in 120 x 80 x 40 mm",
}
SOLID = {"target": {"kind": "closed_solid"}, "quote": "printable in PETG"}
RAIL = b"CASCADE Topology V3, a rail\n"
RAIL_FACTS = Facts(solids=1, volume_mm3=6000.0, box_min=(-15, 0, 0), box_max=(15, 20, 10))
NOT_A_PART = b"CASCADE Topology V3, a face and no solid\n"


def fake_ingest(source: Source) -> Ingested | NotAPart:
    if source.data == NOT_A_PART:
        return NotAPart("it has no solid")
    return Ingested(RAIL_FACTS, source.data)


@dataclass(frozen=True)
class Rows:
    text: str = TEXT
    under_150: dict[str, Any] = field(default_factory=lambda: UNDER_150)
    shelf: dict[str, Any] = field(default_factory=lambda: SHELF)
    envelope: dict[str, Any] = field(default_factory=lambda: ENVELOPE)
    solid: dict[str, Any] = field(default_factory=lambda: SOLID)
    rail: bytes = RAIL
    rail_facts: Facts = RAIL_FACTS
    not_a_part: bytes = NOT_A_PART
