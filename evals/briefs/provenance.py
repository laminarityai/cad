"""Walk every number on a stored scorecard to where it came from, and say what it does not prove.

A scorecard is read as parsed data. The walk visits every quantity on it (a magnitude and a unit)
and every bare int or float, so a number nobody thought of cannot hide in a new field. A number
resolves when a placement rule accepts it. Today there is one: a `Measure` of a check result, which
is either

- computed by a registered check at the version that is current today, or
- read by that check from the materials table, when the check declares the read in `READS`: the
  value equals the table row found by exact key, and the result carries the row's `Source`.

A number in the card's `not_verified` list is the agent's own measurement. It is
`NotVerified`, never resolved, and it fails nothing: ADR-0008 keeps it out of the exit.

Any other number is unresolved: no rule places it. A number of a check scored at an older version,
or against an older table, is stale: score the variant again.

A card as a whole fails when it is bound to no signed build (`binding.bind`), names a
`rebuilt_from` whose signed record pins other code (`binding.link`), is incomplete (no
results, a registered check missing or repeated, an unregistered check, or no number at all), or
fails `confirmation.check_basis`, or has a fit result that `fitted.check_fits` cannot place.

What this does not prove. Stored scorecards are not signed, so a hand-edited value or verdict is not
detected, and a table number that was edited together with the row it should match is not either.
The product ships hosted, so users cannot edit a stored card. The tracer re-runs nothing, so it
shows where a number came from and not that the geometry produced it; `agree.py` checks that.
"""

import math
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import pint
from binding import Unbound, Unlinked, bind, link
from confirmation import BasisFailure, Shown, check_basis
from fitted import Unfitted, check_fits

from cad.briefs.model import limits
from cad.briefs.words import describe
from cad.checks.container.check import Quick
from cad.checks.report import CheckSpec
from cad.checks.result import CheckResult, Measure
from cad.records.roots import Roots
from cad.scorecard.material import ReportedScorecard
from cad.scorecard.model import AgainstBrief, Checked, Scorecard
from cad.sources.fields import SPECS as FIELD_SPECS
from cad.sources.fields import Field
from cad.tables.materials import (
    UNITS,
    FromResearch,
    Known,
    MaterialsTable,
    Source,
    UnknownMaterial,
    magnitude,
)

REL_TOL = 1e-9

type Where = tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class CheckStep:
    check_id: str
    version: str


@dataclass(frozen=True, slots=True)
class TableStep:
    material_key: str
    field: str
    source: Source


@dataclass(frozen=True, slots=True)
class ResearchedStep:
    """A value the server read from a quote on a page it fetched, signed in the project's
    research ledger as record `record`."""

    material_key: str
    field: str
    source: Source
    record: int


@dataclass(frozen=True, slots=True)
class ConfirmedStep:
    """A limit a person confirmed on the page, in the decision the card names."""

    brief_id: str
    decision_sha256: str
    requirement_id: str
    statement: str


@dataclass(frozen=True, slots=True)
class BoundStep:
    """A bound of a research request: the server accepts a researched `field` only in it."""

    field: str
    bound: Literal["low", "high"]


type Step = CheckStep | TableStep | ResearchedStep | ConfirmedStep | BoundStep


@dataclass(frozen=True, slots=True)
class Resolved:
    steps: tuple[Step, ...]


@dataclass(frozen=True, slots=True)
class Stale:
    reason: str


@dataclass(frozen=True, slots=True)
class Unresolved:
    reason: str


@dataclass(frozen=True, slots=True)
class NotVerified:
    """The agent's own measurement: information that no check made and nothing grades."""

    reason: str = "agent's own measurement"


type Outcome = Resolved | Stale | Unresolved | NotVerified


@dataclass(frozen=True, slots=True)
class Traced:
    label: str
    value: str
    outcome: Outcome


@dataclass(frozen=True, slots=True)
class Unreadable:
    reason: str


@dataclass(frozen=True, slots=True)
class Incomplete:
    reason: str


type CardFailure = Unreadable | Unbound | Unlinked | Incomplete | BasisFailure | Unfitted
type BasisKind = Literal["no_brief", "awaiting_confirmation", "against_brief"]


@dataclass(frozen=True, slots=True)
class CardTrace:
    variant_id: str
    failures: tuple[CardFailure, ...]
    numbers: tuple[Traced, ...]
    basis: BasisKind | None = None


@dataclass(frozen=True, slots=True)
class Found:
    where: Where
    value: str


def trace_card(
    card: Scorecard,
    root: Path,
    roots: Roots,
    table: MaterialsTable,
    specs: Mapping[str, CheckSpec],
) -> CardTrace:
    basis = check_basis(roots, card)
    numbers = tuple(
        _place(card, found, table, specs, basis.shown) for found in numbers_in(card.model_dump())
    )
    bound = bind(root, card)
    linked = link(root, card)
    failures = (
        *(() if bound is None else (bound,)),
        *(() if linked is None else (linked,)),
        *_incomplete(card, numbers, specs),
        *basis.failures,
        *check_fits(roots, card),
    )
    return CardTrace(card.variant_id, failures, numbers, card.basis.kind)


def numbers_in(data: object, where: Where = ()) -> Iterator[Found]:
    """Every quantity and every bare int or float in dumped card data, with where it sits."""
    if isinstance(data, Mapping):
        fields = cast(Mapping[str, object], data)
        magnitude = fields.get("magnitude")
        if set(fields) == {"magnitude", "unit"} and isinstance(magnitude, int | float):
            yield Found(where, f"{magnitude:g} {fields['unit']}")
            return
        for name, item in fields.items():
            yield from numbers_in(item, (*where, name))
    elif isinstance(data, list | tuple):
        for index, item in enumerate(cast(Sequence[object], data)):
            yield from numbers_in(item, (*where, index))
    elif isinstance(data, int | float) and not isinstance(data, bool):
        yield Found(where, f"{data:g}")


def _place(
    card: Scorecard,
    found: Found,
    table: MaterialsTable,
    specs: Mapping[str, CheckSpec],
    shown: Shown | None,
) -> Traced:
    path = _path(found.where)
    match found.where:
        case ("results", int() as index, "measured", int() as place, "value"):
            result = card.results[index]
            assert isinstance(result, CheckResult), "only a finished check has measures"
            measure = result.measured[place]
            outcome = _trace(card, result, measure, table, specs)
            return Traced(f"{result.check_id}.{measure.name}", found.value, outcome)
        case ("research", int() as index, "low" | "high" as bound) if isinstance(
            card, ReportedScorecard
        ):
            field = card.research[index].field
            return Traced(path, found.value, _bound(field, bound, found.value))
        case ("basis", "requirements", int() as index, "comparisons", int() as place, "limit"):
            return Traced(path, found.value, _confirmed(card, index, place, shown))
        case ("not_verified", *_):
            return Traced(path, found.value, NotVerified())
        case _:
            pass
    return Traced(path, found.value, Unresolved(f"no rule places a number at {path}"))


def _confirmed(card: Scorecard, index: int, place: int, shown: Shown | None) -> Outcome:
    basis = card.basis
    assert isinstance(basis, AgainstBrief)
    entry = basis.requirements[index]
    assert isinstance(entry, Checked)
    if shown is None:
        return Unresolved(f"the brief store shows no confirmation {basis.decision_sha256[:12]}")
    requirement = next((r for r in shown.requirements if r.id == entry.requirement_id), None)
    if requirement is None:
        return Unresolved(f"requirement {entry.requirement_id} is not in the confirmed set")
    confirmed = limits(requirement.target)
    if place >= len(confirmed):
        return Unresolved(f"requirement {entry.requirement_id} confirmed no limit {place}")
    expected = confirmed[place].quantity
    held = entry.comparisons[place].limit
    if not _same(held, expected):
        return Unresolved(
            f"the card's limit is {held:g~P}, but the person confirmed {expected:g~P}"
        )
    step = ConfirmedStep(
        basis.brief_id, basis.decision_sha256, requirement.id, describe(requirement)
    )
    return Resolved((step,))


def _bound(field: Field, bound: Literal["low", "high"], value: str) -> Outcome:
    if f"{getattr(FIELD_SPECS[field], bound):g}" != value:
        return Unresolved(f"{value} is not the {bound} bound the server sets for {field}")
    return Resolved((BoundStep(field, bound),))


def _same(held: pint.Quantity, expected: pint.Quantity) -> bool:
    unit = str(expected.units)
    try:
        value = magnitude(held, unit)
    except pint.DimensionalityError:
        return False
    return math.isclose(value, magnitude(expected, unit), rel_tol=REL_TOL)


def _path(where: Where) -> str:
    return "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in where)[1:]


def _trace(
    card: Scorecard,
    result: CheckResult,
    measure: Measure,
    table: MaterialsTable,
    specs: Mapping[str, CheckSpec],
) -> Outcome:
    spec = specs.get(result.check_id)
    if spec is None:
        return Unresolved(f"no check called {result.check_id!r} is registered")
    base = measure.name.split(":", 1)[0]
    unit = spec.measures.get(base)
    if unit is None:
        return Unresolved(f"{spec.id} does not declare a measure called {base!r}")
    if measure.value.units != UNITS.Unit(unit):
        return Unresolved(f"{measure.name} is in {measure.value.units:~P}, not {unit}")
    if result.version != spec.version:
        return Stale(
            f"{spec.id} version {result.version[:12]} is not the current {spec.version[:12]}"
        )
    steps: list[Step] = [CheckStep(spec.id, spec.version)]
    field = spec.reads.get(base)
    if field is not None:
        read = _table_step(card, result, measure, field, unit, table)
        if not isinstance(read, TableStep | ResearchedStep):
            return read
        steps.append(read)
    return Resolved(tuple(steps))


def _table_step(
    card: Scorecard,
    result: CheckResult,
    measure: Measure,
    field: str,
    unit: str,
    table: MaterialsTable,
) -> TableStep | ResearchedStep | Stale | Unresolved:
    if card.table_version != table.version:
        return Stale(
            f"scored against materials table {card.table_version[:12]}, "
            f"not the current {table.version[:12]}"
        )
    try:
        material = table.get_material(card.material_key)
    except UnknownMaterial:
        return Unresolved(f"the materials table has no row {card.material_key!r}")
    cited = material.value(field)
    if not isinstance(cited, Known):
        return Unresolved(f"{card.material_key} has no cited {field}: the table says unknown")
    if not math.isclose(measure.value.m_as(unit), cited.magnitude_in(unit), rel_tol=REL_TOL):  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        return Unresolved(
            f"{measure.name} is {measure.value:g~P}, but {card.material_key} {field} "
            f"is {cited.quantity:g~P}"
        )
    if cited.source not in result.sources:
        return Unresolved(f"the {result.check_id} result does not carry the {field} source")
    if isinstance(cited.basis, FromResearch):
        return ResearchedStep(card.material_key, field, cited.source, cited.basis.record)
    return TableStep(card.material_key, field, cited.source)


def _incomplete(
    card: Scorecard, numbers: tuple[Traced, ...], specs: Mapping[str, CheckSpec]
) -> Iterator[Incomplete]:
    if not card.results:
        yield Incomplete("the card has no results")
    seen = Counter((result.check_id, result.instance) for result in card.results)
    ran = {check_id for check_id, _ in seen}
    for check_id, spec in specs.items():
        if isinstance(spec.budget, Quick) and check_id not in ran and card.results:
            yield Incomplete(f"no result for the registered check {check_id}")
    for (check_id, instance), count in seen.items():
        if count > 1:
            named = f" for load case {instance}" if instance else ""
            yield Incomplete(f"{count} results for {check_id}{named}")
    for check_id in sorted(ran - set(specs)):
        yield Incomplete(f"a result for {check_id}, which is not a registered check")
    if not numbers:
        yield Incomplete("the card holds no number")
