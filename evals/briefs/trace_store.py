"""Trace every number on every scorecard stored in a variant store.

    uv run python evals/briefs/trace_store.py                  # the store under ~/.cad/variants
    uv run python evals/briefs/trace_store.py --root DIR       # another store
    uv run python evals/briefs/trace_store.py --steps          # print each number's chain

Each card is read, bound to its signed build, checked for completeness, and every number on it is
traced (see `provenance`). The summary counts each kind of failure on its own line. Exit code 1
means at least one card or number failed, or the store holds no card or no number: a pass over
nothing proves nothing.

Limit: stored cards are unsigned, so a hand-edited value or verdict is not detected. The product
ships hosted, so users cannot edit them.
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from binding import Unbound
from provenance import (
    CardFailure,
    CardTrace,
    CheckStep,
    Incomplete,
    Resolved,
    Stale,
    TableStep,
    Traced,
    Unreadable,
    Unresolved,
    trace_card,
)
from pydantic import ValidationError
from tracking import RequirementOutcome, describe, outcomes_of, track

from cad.checks.report import SPECS
from cad.scorecard.model import Scorecard
from cad.scorecard.score import SCORECARD
from cad.tables.materials import MaterialsTable, load_materials
from cad.variants import entry

SPEC_BY_ID: Final = {spec.id: spec for spec in SPECS}


@dataclass(frozen=True, slots=True)
class Tally:
    cards: int
    unreadable: int
    unbound: int
    incomplete: int
    numbers: int
    resolved: int
    stale: int
    unresolved: int


def tally(traces: Sequence[CardTrace]) -> Tally:
    numbers = [one.outcome for trace in traces for one in trace.numbers]
    return Tally(
        cards=len(traces),
        unreadable=_cards_with(traces, Unreadable),
        unbound=_cards_with(traces, Unbound),
        incomplete=_cards_with(traces, Incomplete),
        numbers=len(numbers),
        resolved=sum(isinstance(outcome, Resolved) for outcome in numbers),
        stale=sum(isinstance(outcome, Stale) for outcome in numbers),
        unresolved=sum(isinstance(outcome, Unresolved) for outcome in numbers),
    )


def _cards_with(traces: Sequence[CardTrace], kind: type[CardFailure]) -> int:
    return sum(any(isinstance(failure, kind) for failure in trace.failures) for trace in traces)


def exit_code(counts: Tally) -> int:
    failed = (
        counts.unreadable + counts.unbound + counts.incomplete + counts.stale + counts.unresolved
    )
    return 1 if failed or not counts.cards or not counts.numbers else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trace_store", description="Trace every number on every stored scorecard."
    )
    parser.add_argument("--root", type=Path, default=entry.VARIANTS_ROOT, help="the variant store")
    parser.add_argument("--steps", action="store_true", help="print the chain of every number")
    args = parser.parse_args(argv)
    paths = sorted(
        path
        for path in args.root.glob(f"*/{SCORECARD}")
        if entry.ID_PATTERN.fullmatch(path.parent.name)
    )
    table = load_materials()
    traces: list[CardTrace] = []
    outcomes: list[RequirementOutcome] = []
    for path in paths:
        trace, found = _read(path, args.root, table)
        _print(trace, args.steps)
        traces.append(trace)
        outcomes.extend(found)
    counts = tally(traces)
    tracking = track(tuple(outcomes))
    print(f"cards: {counts.cards}, numbers: {counts.numbers}")
    print(
        f"cards unreadable: {counts.unreadable}, unbound: {counts.unbound}, "
        f"incomplete: {counts.incomplete}"
    )
    print(
        f"numbers resolved: {counts.resolved}, stale: {counts.stale}, "
        f"unresolved: {counts.unresolved}"
    )
    print(f"strict pass rate: {describe(tracking.strict_pass_rate)}")
    print(f"requirements covered by reviewed checks: {describe(tracking.reviewed_coverage)}")
    if not counts.cards:
        print(f"no scorecard under {args.root}")
    elif not counts.numbers:
        print("no number on any scorecard")
    return exit_code(counts)


def _read(
    path: Path, root: Path, table: MaterialsTable
) -> tuple[CardTrace, tuple[RequirementOutcome, ...]]:
    name = path.parent.name
    try:
        card = Scorecard.model_validate_json(path.read_text())
    except (OSError, ValidationError) as error:
        return CardTrace(name, (Unreadable(str(error).splitlines()[0]),), ()), ()
    trace = trace_card(card, root, table, SPEC_BY_ID)
    if card.variant_id != name:
        misplaced = Unbound(f"the card names variant {card.variant_id} but is stored under {name}")
        trace = CardTrace(name, (misplaced, *trace.failures), trace.numbers)
    return trace, outcomes_of(card)


def _print(trace: CardTrace, steps: bool) -> None:
    broken = [one for one in trace.numbers if not isinstance(one.outcome, Resolved)]
    failed = bool(trace.failures or broken)
    print(f"{'FAIL' if failed else 'ok  '} {trace.variant_id}: {len(trace.numbers)} numbers")
    for failure in trace.failures:
        print(f"     {type(failure).__name__.upper()} {failure.reason}")
    for one in trace.numbers if steps else broken:
        print(f"     {_line(one)}")


def _line(one: Traced) -> str:
    head = f"{one.label} = {one.value}"
    outcome = one.outcome
    if isinstance(outcome, Stale | Unresolved):
        return f"{type(outcome).__name__.upper()} {head}: {outcome.reason}"
    chain = " -> ".join(_step(step) for step in outcome.steps)
    return f"{head} -> {chain}"


def _step(step: CheckStep | TableStep) -> str:
    if isinstance(step, CheckStep):
        return f"computed by check {step.check_id} at version {step.version[:12]}"
    return f"table {step.material_key}.{step.field}, {step.source.title}, {step.source.page}"


if __name__ == "__main__":
    sys.exit(main())
