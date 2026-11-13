"""Place the numbers of a row the scorecard shows with no verdict: a stated target that waits for
the person's Confirm, or a value the agent assumed.

A row's own number resolves to the brief store record that holds it, found by exact key: an
awaiting row's requirement id in a stored proposal, an assumed row's check and instance in a
numbered assumption set. A card shows the set in force when it was scored, and no set is edited
once stored. Both are the agent's numbers, so the step says so and never names a
confirmation. A row's measured number must equal the measure that the row's result holds on the
same card, and then traces as that measure does.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pint
from cardnumbers import Where
from chain import AssumedStep, Outcome, ProposedStep, Resolved, Unresolved
from confirmation import REFUSED
from measures import Measuring, same, trace_measure

from cad.briefs import assumptions
from cad.briefs import store as briefs
from cad.briefs.assumptions import AssumptionSet
from cad.briefs.holes import FastenerHoles, PlainHoles
from cad.briefs.model import Requirement, deciding_check, limits
from cad.briefs.words import describe
from cad.checks.report import CheckSpec
from cad.records.roots import Roots
from cad.scorecard.assumed import AssumedRow
from cad.scorecard.awaiting import AwaitingRow
from cad.scorecard.holes import MEASURE, band
from cad.scorecard.material import ReportedScorecard
from cad.scorecard.model import AgainstBrief, AwaitingConfirmation, PendingCheck, Scorecard
from cad.scorecard.requirements import instance, result_of
from cad.scorecard.unjudged import Reported
from cad.tables.materials import UNITS, MaterialsTable


@dataclass(frozen=True, slots=True)
class Held:
    """What the brief store holds for the card's brief: every proposed requirement by id, with
    the number of the newest proposal that holds it, and every numbered assumption set."""

    brief_id: str
    proposed: Mapping[str, tuple[int, Requirement]]
    assumed: tuple[AssumptionSet, ...]
    problem: str | None = None


def held(roots: Roots, card: Scorecard) -> Held | None:
    basis = card.basis
    if not isinstance(card, ReportedScorecard) or not (card.awaiting or card.assumptions):
        return None
    if not isinstance(basis, AwaitingConfirmation | AgainstBrief):
        return None
    try:
        state = briefs.read_state(roots, basis.brief_id)
        sets = assumptions.every_set(roots, basis.brief_id)
    except REFUSED as error:
        return Held(basis.brief_id, {}, (), str(error))
    proposed: dict[str, tuple[int, Requirement]] = {
        requirement.id: (one.proposal.number, requirement)
        for one in state.proposals
        for requirement in one.proposal.requirements
    }
    return Held(basis.brief_id, proposed, sets)


def place(
    card: Scorecard,
    where: Where,
    store: Held | None,
    table: MaterialsTable,
    specs: Mapping[str, CheckSpec],
) -> Outcome | None:
    """The outcome of a number in a row, or None when `where` is not in a row."""
    if not isinstance(card, ReportedScorecard) or store is None:
        return None
    match where:
        case ("awaiting", int() as index, "values", int() as place, "proposed"):
            return _proposed(card.awaiting[index], place, store)
        case ("awaiting", int() as index, "holes", "count" | "low" | "high" as bound):
            return _band(card.awaiting[index], bound, store)
        case ("awaiting", int() as index, "values", int() as place, "measured"):
            row = card.awaiting[index]
            value = row.values[place]
            assert value.measured is not None
            return _measured(card, row, value.measure, value.measured, table, specs)
        case ("awaiting", int() as index, "holes", "measured", int() as place):
            return _hole(card, card.awaiting[index], place, table, specs)
        case ("assumptions", int() as index, "values", int() as place, "assumed"):
            return _assumed(card.assumptions[index], place, store)
        case ("assumptions", int() as index, "values", int() as place, "measured"):
            row = card.assumptions[index]
            value = row.values[place]
            assert value.measured is not None
            return _measured(card, row, value.measure, value.measured, table, specs)
        case _:
            return None


def _requirement(row: AwaitingRow, store: Held) -> Requirement | Unresolved:
    if store.problem is not None:
        return Unresolved(store.problem)
    found = store.proposed.get(row.requirement_id)
    if found is None:
        return Unresolved(f"no proposal for brief {store.brief_id} holds {row.requirement_id}")
    _, requirement = found
    target = requirement.target
    if (deciding_check(target), instance(target)) != (row.check_id, row.instance):
        return Unresolved(
            f"requirement {row.requirement_id} is decided by {deciding_check(target)}, "
            f"not the {row.check_id} result the row names"
        )
    return requirement


def _proposed_step(requirement: Requirement, store: Held) -> Resolved:
    number, _ = store.proposed[requirement.id]
    step = ProposedStep(store.brief_id, number, requirement.id, describe(requirement))
    return Resolved((step,))


def _proposed(row: AwaitingRow, place: int, store: Held) -> Outcome:
    requirement = _requirement(row, store)
    if isinstance(requirement, Unresolved):
        return requirement
    shown = row.values[place]
    proposed = limits(requirement.target)
    if place >= len(proposed) or proposed[place].measure != shown.measure:
        return Unresolved(f"requirement {requirement.id} proposed no {shown.measure} limit")
    if not same(shown.proposed, proposed[place].quantity):
        return Unresolved(
            f"the row says {shown.proposed:g~P}, but the agent proposed "
            f"{proposed[place].quantity:g~P}"
        )
    return _proposed_step(requirement, store)


def _band(row: AwaitingRow, bound: str, store: Held) -> Outcome:
    requirement = _requirement(row, store)
    if isinstance(requirement, Unresolved):
        return requirement
    target = requirement.target
    if row.holes is None or not isinstance(target, FastenerHoles | PlainHoles):
        return Unresolved(f"requirement {requirement.id} proposed no holes")
    if bound == "count":
        if row.holes.count != target.count:
            return Unresolved(f"the row counts {row.holes.count} holes, not {target.count}")
        return _proposed_step(requirement, store)
    wanted = band(target)
    expected = UNITS.Quantity(wanted.low if bound == "low" else wanted.high, "mm")
    shown = row.holes.low if bound == "low" else row.holes.high
    if not same(shown, expected):
        return Unresolved(f"the row's {bound} is {shown:g~P}, but the band is {expected:g~P}")
    return _proposed_step(requirement, store)


def _assumed(row: AssumedRow, place: int, store: Held) -> Outcome:
    if store.problem is not None:
        return Unresolved(store.problem)
    shown = row.values[place]
    for held in reversed(store.assumed):
        for one in held.assumptions:
            target = one.target
            assumed = limits(target)
            if (
                (deciding_check(target), instance(target)) == (row.check_id, row.instance)
                and place < len(assumed)
                and assumed[place].measure == shown.measure
                and same(shown.assumed, assumed[place].quantity)
            ):
                step = AssumedStep(store.brief_id, held.number, row.check_id, row.instance)
                return Resolved((step,))
    return Unresolved(
        f"no assumption set of brief {store.brief_id} assumes {shown.assumed:g~P} "
        f"for {row.check_id}"
    )


def _measured(
    card: ReportedScorecard,
    row: AwaitingRow | AssumedRow,
    name: str,
    shown: pint.Quantity,
    table: MaterialsTable,
    specs: Mapping[str, CheckSpec],
) -> Outcome:
    result = _result(card.results, row)
    if isinstance(result, Unresolved):
        return result
    measure = next((one for one in result.measured if one.name == name), None)
    if measure is None:
        return Unresolved(f"the {row.check_id} result has no measure {name}")
    if not same(shown, measure.value):
        return Unresolved(
            f"the row says {shown:g~P}, but {row.check_id} measured {measure.value:g~P}"
        )
    return trace_measure(card, result, measure, table, specs)


def _hole(
    card: ReportedScorecard,
    row: AwaitingRow,
    place: int,
    table: MaterialsTable,
    specs: Mapping[str, CheckSpec],
) -> Outcome:
    assert row.holes is not None
    result = _result(card.results, row)
    if isinstance(result, Unresolved):
        return result
    named = [one for one in result.measured if one.name.startswith(f"{MEASURE}:")]
    shown = row.holes.measured[place]
    if place >= len(named) or not same(shown, named[place].value):
        return Unresolved(f"the {row.check_id} result measured no hole of {shown:g~P} there")
    return trace_measure(card, result, named[place], table, specs)


def _result(results: Sequence[Reported], row: AwaitingRow | AssumedRow) -> Measuring | Unresolved:
    result = result_of(results, row.check_id, row.instance)
    if result is None or isinstance(result, PendingCheck):
        named = f" for {row.instance}" if row.instance else ""
        return Unresolved(f"the card has no finished {row.check_id} result{named}")
    return result
