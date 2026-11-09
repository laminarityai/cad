"""Prove that confirmed targets conflict, before any build, by interval arithmetic over one
quantity at a time. Every number comes from a confirmed target or a table row read by exact key;
an unknown value gives no bound, and nothing here is guessed or researched."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from cad.auto.model import Bounds, Read
from cad.briefs.model import Envelope, MadeOf, MaxMass, MeasureLimit, MinMass, Requirement
from cad.checks.result import Comparator
from cad.scorecard.requirements import UNIT_CONVERSION_NOISE
from cad.tables.materials import FromResearch, Known, MaterialsTable, magnitude

VOLUME: Final = ("mass", "volume")


@dataclass(frozen=True, slots=True)
class _Bound:
    value: float
    words: str
    requirements: tuple[str, ...]
    reads: tuple[Read, ...] = ()


def bounds_conflicts(
    requirements: Sequence[Requirement], table: MaterialsTable
) -> tuple[Bounds, ...]:
    volume_hi: list[_Bound] = []
    volume_lo: list[_Bound] = []
    mass_hi: list[_Bound] = []
    mass_lo: list[_Bound] = []
    made_of: Requirement | None = None
    for one in requirements:
        rid = (one.id,)
        match one.target:
            case Envelope(edges=edges):
                volume = math.prod(magnitude(edge, "mm") for edge in edges)
                volume_hi.append(_Bound(volume, f"envelope {_cm3(volume)}", rid))
            case MeasureLimit() as limit if (limit.check_id, limit.measure) == VOLUME:
                volume = magnitude(limit.limit, "mm^3")
                if limit.comparator is Comparator.AT_MOST:
                    volume_hi.append(_Bound(volume, f"volume at most {_cm3(volume)}", rid))
                else:
                    volume_lo.append(_Bound(volume, f"volume at least {_cm3(volume)}", rid))
            case MaxMass(mass=mass):
                grams = magnitude(mass, "g")
                mass_hi.append(_Bound(grams, f"max_mass {grams:g} g", rid))
            case MinMass(mass=mass):
                grams = magnitude(mass, "g")
                mass_lo.append(_Bound(grams, f"min_mass {grams:g} g", rid))
            case MadeOf():
                made_of = one
            case _:
                pass
    found = [_conflict("volume", volume_lo, volume_hi)]
    tightest = min(volume_hi, key=lambda bound: bound.value, default=None)
    if made_of is not None and tightest is not None:
        through = _mass_from_volume(made_of, tightest, table)
        if through is not None:
            mass_hi.append(through)
    found.append(_conflict("mass", mass_lo, mass_hi))
    return tuple(one for one in found if one is not None)


def _mass_from_volume(made_of: Requirement, volume: _Bound, table: MaterialsTable) -> _Bound | None:
    assert isinstance(made_of.target, MadeOf)
    key = table.row_key(made_of.target.material)
    density = table.get_material(key).density
    if not isinstance(density, Known):
        return None
    per_cm3 = density.magnitude_in("g/cm^3")
    grams = per_cm3 * volume.value / 1000
    basis: Literal["table", "researched"] = (
        "researched" if isinstance(density.basis, FromResearch) else "table"
    )
    read = Read(material_key=key, field="density", value=f"{per_cm3:g} g/cm³", basis=basis)
    return _Bound(
        grams,
        f"density({key}) {read.value} \N{MULTIPLICATION SIGN} {volume.words} = {grams:g} g",
        (made_of.id, *volume.requirements),
        (read,),
    )


def _conflict(
    quantity: Literal["mass", "volume"], lows: list[_Bound], highs: list[_Bound]
) -> Bounds | None:
    lo = max(lows, key=lambda bound: bound.value, default=None)
    hi = min(highs, key=lambda bound: bound.value, default=None)
    if lo is None or hi is None or lo.value <= hi.value * (1 + UNIT_CONVERSION_NOISE):
        return None
    return Bounds(
        quantity=quantity,
        statement=f"{lo.words} > {hi.words}",
        requirements=tuple(dict.fromkeys((*lo.requirements, *hi.requirements))),
        reads=(*lo.reads, *hi.reads),
    )


def _cm3(mm3: float) -> str:
    return f"{mm3 / 1000:g} cm³"
