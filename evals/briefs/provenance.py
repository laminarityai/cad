"""Walk every number on a stored scorecard to where it came from, and say what it does not prove.

A scorecard is read as parsed data. The walk visits every quantity on it (a magnitude and a unit)
and every bare int or float, so a number nobody thought of cannot hide in a new field. A number
resolves when a placement rule accepts it:

- a `Measure` of a check result, finished or measure-only, by `measures.trace_measure`;
- a limit the person confirmed, or a research request's bound the server sets;
- a number in a row with no verdict, a proposal waiting on the person or an assumption, by
  `rows.place`. The row's own number is the agent's, and the step says so.

A number in the card's `not_verified` list is the agent's own measurement. It is
`NotVerified`, never resolved, and it fails nothing: ADR-0008 keeps it out of the exit.

The result and inputs of an approved agent-written check (ADR-0011) are `AgentCheckedNumber`,
counted apart and never resolved. Its limit resolves to the person's confirmation.

Any other number is unresolved: no rule places it. A number of a check scored at an older version,
or against an older table, is stale: score the variant again.

A card as a whole fails when it is bound to no signed build (`binding.bind`), names a
`rebuilt_from` whose signed record pins other code (`binding.link`), is incomplete (no
results, a registered check missing or repeated, an unregistered check, or no number at all), or
fails `confirmation.check_basis`, or has a fit result that `fitted.check_fits` cannot place.

A card is not signed, so each result on a card the session was shown must equal the server's
reading of the same variant, material and brief (`measures.trace_measure`), which rests on the
stored, signed job result. A changed value or verdict, or another variant's results, is then
unresolved. A reading is compared with nothing, since it is the server's own card.

What this does not prove. `trace_store.py` run over a transcript alone reads nothing from the
server, so it does not detect a hand-edited value or verdict. A table number that was edited
together with the row it should match is not detected either. The tracer re-runs nothing, so it
shows where a number came from and not that the geometry produced it; `agree.py` checks that.
"""

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import rows
from binding import Unbound, Unlinked, bind, link
from cardnumbers import Found, numbers_in, path_of
from chain import (
    AgentCheckedNumber,
    BoundStep,
    ConfirmedStep,
    NotVerified,
    Outcome,
    Resolved,
    Unresolved,
)
from confirmation import BasisFailure, Shown, check_basis
from fitted import Unfitted, check_fits
from measures import Reading, same, trace_measure

from cad.briefs.holes import FastenerHoles, PlainHoles
from cad.briefs.model import AgentLimit, Requirement, limits
from cad.briefs.words import describe
from cad.checks.container.check import Quick
from cad.checks.report import CheckSpec
from cad.records.roots import Roots
from cad.scorecard.holes import band
from cad.scorecard.material import ReportedScorecard
from cad.scorecard.model import (
    AgainstBrief,
    AgentChecked,
    AwaitingConfirmation,
    Checked,
    PendingCheck,
    Scorecard,
)
from cad.scorecard.unjudged import Reported
from cad.tables.fields import FIELDS, Field
from cad.tables.materials import UNITS, MaterialsTable


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
    brief_id: str | None = None


def trace_card(
    card: Scorecard,
    root: Path,
    roots: Roots,
    table: MaterialsTable,
    specs: Mapping[str, CheckSpec],
    reading: Reading,
) -> CardTrace:
    basis = check_basis(roots, card)
    store = rows.held(roots, card)
    numbers = tuple(
        _place(card, found, table, specs, basis.shown, store, reading)
        for found in numbers_in(card.model_dump())
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
    named = (
        card.basis.brief_id if isinstance(card.basis, AgainstBrief | AwaitingConfirmation) else None
    )
    return CardTrace(card.variant_id, failures, numbers, card.basis.kind, named)


def _place(
    card: Scorecard,
    found: Found,
    table: MaterialsTable,
    specs: Mapping[str, CheckSpec],
    shown: Shown | None,
    store: rows.Held | None,
    reading: Reading,
) -> Traced:
    path = path_of(found.where)
    match found.where:
        case ("results", int() as index, "measured", int() as place, "value"):
            results: Sequence[Reported] = card.results
            result = results[index]
            assert not isinstance(result, PendingCheck), "a pending check has no measures"
            measure = result.measured[place]
            outcome = trace_measure(card, result, measure, table, specs, reading)
            return Traced(f"{result.check_id}.{measure.name}", found.value, outcome)
        case ("research", int() as index, "low" | "high" as bound) if isinstance(
            card, ReportedScorecard
        ):
            field = card.research[index].field
            return Traced(path, found.value, _bound(field, bound, found.value))
        case ("basis", "requirements", int() as index, "comparisons", int() as place, "limit"):
            return Traced(path, found.value, _confirmed(card, index, place, shown))
        case ("basis", "requirements", int() as index, "limit"):
            return Traced(path, found.value, _agent_limit(card, index, shown))
        case ("basis", "requirements", int() as index, "value" | "inputs", *_):
            return Traced(path, found.value, AgentCheckedNumber())
        case ("not_verified", *_):
            return Traced(path, found.value, NotVerified())
        case _:
            pass
    in_row = rows.place(card, found.where, store, table, specs, reading)
    if in_row is not None:
        return Traced(path, found.value, in_row)
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
    if isinstance(requirement.target, FastenerHoles | PlainHoles):
        return _band(entry, requirement, place, basis.brief_id, basis.decision_sha256)
    confirmed = limits(requirement.target)
    if place >= len(confirmed):
        return Unresolved(f"requirement {entry.requirement_id} confirmed no limit {place}")
    expected = confirmed[place].quantity
    held = entry.comparisons[place].limit
    if not same(held, expected):
        return Unresolved(
            f"the card's limit is {held:g~P}, but the person confirmed {expected:g~P}"
        )
    step = ConfirmedStep(
        basis.brief_id, basis.decision_sha256, requirement.id, describe(requirement)
    )
    return Resolved((step,))


def _agent_limit(card: Scorecard, index: int, shown: Shown | None) -> Outcome:
    """The person's confirmed number, or the check's own when its source writes the limit."""
    basis = card.basis
    assert isinstance(basis, AgainstBrief)
    entry = basis.requirements[index]
    assert isinstance(entry, AgentChecked)
    if shown is None:
        return Unresolved(f"the brief store shows no confirmation {basis.decision_sha256[:12]}")
    requirement = next((r for r in shown.requirements if r.id == entry.requirement_id), None)
    if requirement is None:
        return Unresolved(f"requirement {entry.requirement_id} is not in the confirmed set")
    target = requirement.target
    if not isinstance(target, AgentLimit):
        return Unresolved(f"requirement {entry.requirement_id} confirmed no agent-written limit")
    if target.limit is None:
        return AgentCheckedNumber()
    if not same(entry.limit, target.limit):
        return Unresolved(
            f"the card's limit is {entry.limit:g~P}, but the person confirmed {target.limit:g~P}"
        )
    confirmed = ConfirmedStep(
        basis.brief_id, basis.decision_sha256, requirement.id, describe(requirement)
    )
    return Resolved((confirmed,))


def _band(
    entry: Checked, requirement: Requirement, place: int, brief_id: str, decision_sha256: str
) -> Outcome:
    """A holes requirement's band is the confirmed target read through the fasteners table by its
    exact key, or the confirmed diameter with the fixed tolerance, so the card's two limits must
    equal it."""
    assert isinstance(requirement.target, FastenerHoles | PlainHoles)
    wanted = band(requirement.target)
    expected = UNITS.Quantity((wanted.low, wanted.high)[place], "mm")
    held = entry.comparisons[place].limit
    if not same(held, expected):
        return Unresolved(f"the card's limit is {held:g~P}, but the band is {expected:g~P}")
    return Resolved(
        (ConfirmedStep(brief_id, decision_sha256, requirement.id, describe(requirement)),)
    )


def _bound(field: Field, bound: Literal["low", "high"], value: str) -> Outcome:
    if f"{getattr(FIELDS[field], bound):g}" != value:
        return Unresolved(f"{value} is not the {bound} bound the server sets for {field}")
    return Resolved((BoundStep(field, bound),))


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
