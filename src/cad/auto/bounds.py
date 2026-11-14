"""Requirements whose bounds no design can meet together, said in the words the person reads.

Each quantity gathers its lower and upper bounds, and a bound on one body is a quantity of its own.
Mass also gains the upper bound that the material's density puts on it inside the tightest volume,
when the table knows the density and one made_of names the material of every body."""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, assert_never

from cad.auto.model import Bounds, Read
from cad.briefs.bindable import BINDABLE
from cad.briefs.holes import FastenerHoles, PlainHoles
from cad.briefs.model import (
    AgentLimit,
    ClosedSolid,
    Envelope,
    FitsWith,
    MadeOf,
    MaxClearance,
    MaxDeflection,
    MaxMass,
    MeasureLimit,
    MinClearance,
    MinMass,
    MinSafetyFactor,
    Requirement,
    Unchecked,
    amount,
)
from cad.checks.result import Comparator
from cad.sandbox.on_body import per_body
from cad.scorecard.requirements import UNIT_CONVERSION_NOISE
from cad.tables.materials import FromResearch, Known, MaterialsTable, magnitude

MASS: Final = "mass"
VOLUME: Final = "volume"
_VOLUME_MEASURE: Final = ("mass", "volume")


@dataclass(frozen=True, slots=True)
class _Bound:
    """`words` finishes "but ..." for an upper bound and starts the sentence for a lower one.
    `space` names a volume upper bound as the room a material fills."""

    value: float
    words: str
    requirements: tuple[str, ...]
    reads: tuple[Read, ...] = ()
    space: str = ""


@dataclass(frozen=True, slots=True)
class Unweighed:
    """A material whose density is unknown, so a mass bound inside a volume is not checked."""

    statement: str
    requirements: tuple[str, ...]


@dataclass
class _Gathered:
    lows: defaultdict[str, list[_Bound]]
    highs: defaultdict[str, list[_Bound]]
    made_of: Requirement | None = None
    on_a_body: bool = False

    @property
    def pin(self) -> Requirement | None:
        """The made_of every body is made of. A made_of on one body leaves the rest unknown."""
        return None if self.on_a_body else self.made_of


def bounds_conflicts(
    requirements: Sequence[Requirement], table: MaterialsTable
) -> tuple[Bounds, ...]:
    gathered = _gather(requirements)
    through = _through_density(gathered, table)
    if through is not None:
        gathered.highs[MASS].append(through)
    quantities = dict.fromkeys((*gathered.lows, *gathered.highs))
    found = (_conflict(one, gathered.lows[one], gathered.highs[one]) for one in quantities)
    return tuple(one for one in found if one is not None)


def unweighed(requirements: Sequence[Requirement], table: MaterialsTable) -> Unweighed | None:
    """The note for a minimum mass inside a volume when the material has no density yet. It
    says the pair is not checked, never that it can or cannot be met."""
    gathered = _gather(requirements)
    lowest = max(gathered.lows[MASS], key=lambda bound: bound.value, default=None)
    room = min(gathered.highs[VOLUME], key=lambda bound: bound.value, default=None)
    made_of = gathered.pin
    if made_of is None or lowest is None or room is None:
        return None
    assert isinstance(made_of.target, MadeOf)
    key = table.row_key(made_of.target.material)
    if isinstance(table.get_material(key).density, Known):
        return None
    return Unweighed(
        f"{table.name_of(key)} has no density yet, so whether the mass can be at least "
        f"{lowest.value:g} g within {room.space} is not checked until its density is researched",
        tuple(dict.fromkeys((*lowest.requirements, made_of.id, *room.requirements))),
    )


def _gather(requirements: Sequence[Requirement]) -> _Gathered:
    gathered = _Gathered(defaultdict(list), defaultdict(list))
    for one in requirements:
        rid = (one.id,)
        match one.target:
            case Envelope(edges=edges):
                box = " x ".join(f"{magnitude(edge, 'mm'):g}" for edge in edges)
                volume = math.prod(magnitude(edge, "mm") for edge in edges)
                space = f"the whole {box} mm box ({_cm3(volume)})"
                words = f"the whole {box} mm box holds {_cm3(volume)}"
                gathered.highs[VOLUME].append(_Bound(volume, words, rid, space=space))
            case MeasureLimit() as limit:
                _gather_limit(gathered, limit, rid)
            case MaxMass(mass=mass, body=body):
                grams = magnitude(mass, "g")
                gathered.highs[per_body(MASS, body)].append(
                    _Bound(grams, _on(body, f"the mass must be at most {grams:g} g"), rid)
                )
            case MinMass(mass=mass, body=body):
                grams = magnitude(mass, "g")
                gathered.lows[per_body(MASS, body)].append(
                    _Bound(grams, _on(body, f"the mass must be at least {grams:g} g"), rid)
                )
            case MadeOf(body=None):
                gathered.made_of = one
            case MadeOf():
                gathered.on_a_body = True
            case (
                ClosedSolid()
                | Unchecked()
                | MinSafetyFactor()
                | MaxDeflection()
                | MinClearance()
                | MaxClearance()
                | FastenerHoles()
                | PlainHoles()
                | FitsWith()
                | AgentLimit()
            ):
                pass
            case _:
                assert_never(one.target)
    return gathered


def _gather_limit(gathered: _Gathered, limit: MeasureLimit, rid: tuple[str, ...]) -> None:
    key = (limit.check_id, limit.measure)
    bindable = BINDABLE[key]
    value = magnitude(limit.limit, bindable.unit)
    whole = VOLUME if key == _VOLUME_MEASURE else f"{limit.check_id}:{limit.measure}"
    quantity = per_body(whole, limit.body)
    if limit.comparator is Comparator.AT_MOST:
        words = _on(limit.body, f"{bindable.words} must be at most {amount(limit.limit)}")
        space = f"the most volume allowed ({amount(limit.limit)})"
        gathered.highs[quantity].append(_Bound(value, words, rid, space=space))
    else:
        words = _on(limit.body, f"{bindable.words} must be at least {amount(limit.limit)}")
        gathered.lows[quantity].append(_Bound(value, words, rid))


def _through_density(gathered: _Gathered, table: MaterialsTable) -> _Bound | None:
    made_of = gathered.pin
    room = min(gathered.highs[VOLUME], key=lambda bound: bound.value, default=None)
    if made_of is None or room is None:
        return None
    assert isinstance(made_of.target, MadeOf)
    key = table.row_key(made_of.target.material)
    density = table.get_material(key).density
    if not isinstance(density, Known):
        return None
    per_cm3 = density.magnitude_in("g/cm^3")
    grams = per_cm3 * room.value / 1000
    basis: Literal["table", "researched"] = (
        "researched" if isinstance(density.basis, FromResearch) else "table"
    )
    read = Read(material_key=key, field="density", value=f"{per_cm3:g} g/cm³", basis=basis)
    return _Bound(
        grams,
        f"{table.name_of(key)} at {read.value} weighs {grams:g} g filling {room.space}",
        (made_of.id, *room.requirements),
        (read,),
    )


def _conflict(quantity: str, lows: list[_Bound], highs: list[_Bound]) -> Bounds | None:
    lo = max(lows, key=lambda bound: bound.value, default=None)
    hi = min(highs, key=lambda bound: bound.value, default=None)
    if lo is None or hi is None or lo.value <= hi.value * (1 + UNIT_CONVERSION_NOISE):
        return None
    return Bounds(
        quantity=quantity,
        statement=f"{_capital(lo.words)}, but {hi.words}",
        requirements=tuple(dict.fromkeys((*lo.requirements, *hi.requirements))),
        reads=(*lo.reads, *hi.reads),
    )


def _on(body: str | None, words: str) -> str:
    return words if body is None else f"for the {body}, {words}"


def _capital(words: str) -> str:
    return words[:1].upper() + words[1:]


def _cm3(mm3: float) -> str:
    return f"{mm3 / 1000:g} cm³"
