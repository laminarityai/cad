"""Trace every number on every scorecard a session was shown.

    uv run python evals/briefs/trace_store.py TRANSCRIPT... [--root DIR] [--briefs-root DIR]
        [--projects-root DIR] [--steps] [--require-judged]

The cards are the results of score_variant and scorecard calls in the transcripts (see
`transcript_cards`). Each card is read, bound to its signed build, checked for completeness, its
basis is checked against the brief and project stores, and every number on it is traced (see
`provenance`). The summary counts each kind of failure on its own line, and counts cards judged
against a brief apart from cards awaiting confirmation and cards with no brief. Exit code 1 means
at least one card or number failed, or the transcripts hold no card or no number: a pass over
nothing proves nothing. With `--require-judged`, a card awaiting confirmation or with no brief
fails too.

Limit: a transcript is unsigned, so a hand-edited card is not detected.
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, assert_never

import pint
from binding import Unbound, Unlinked
from confirmation import Misjudged, Superseded, Unconfirmed
from fitted import Unfitted
from provenance import (
    AgentCheckedNumber,
    BoundStep,
    CardFailure,
    CardTrace,
    CheckStep,
    ConfirmedStep,
    Incomplete,
    NotVerified,
    ResearchedStep,
    Resolved,
    Stale,
    Step,
    TableStep,
    Traced,
    Unreadable,
    Unresolved,
    trace_card,
)
from pydantic import ValidationError
from tracking import RequirementOutcome, describe, describe_apart, outcomes_of, track
from transcript_cards import read_cards

from cad.briefs import store as briefs
from cad.briefs.store import BriefRefused
from cad.checks.report import SPECS
from cad.records.roots import HOME_ROOTS, Roots
from cad.research.overlay import project_table, table_named
from cad.scorecard import material
from cad.scorecard.model import AgainstBrief, AwaitingConfirmation, Scorecard
from cad.tables.materials import MaterialsTable, load_materials
from cad.variants import entry

SPEC_BY_ID: Final = {spec.id: spec for spec in SPECS}


@dataclass(frozen=True, slots=True)
class Tally:
    cards: int
    unreadable: int
    unbound: int
    unlinked: int
    incomplete: int
    unconfirmed: int
    misjudged: int
    superseded: int
    unfitted: int
    judged: int
    awaiting: int
    no_brief: int
    numbers: int
    resolved: int
    stale: int
    unresolved: int
    not_verified: int
    agent_checked: int


def tally(traces: Sequence[CardTrace]) -> Tally:
    numbers = [one.outcome for trace in traces for one in trace.numbers]
    bases = [trace.basis for trace in traces]
    return Tally(
        cards=len(traces),
        unreadable=_cards_with(traces, Unreadable),
        unbound=_cards_with(traces, Unbound),
        unlinked=_cards_with(traces, Unlinked),
        incomplete=_cards_with(traces, Incomplete),
        unconfirmed=_cards_with(traces, Unconfirmed),
        misjudged=_cards_with(traces, Misjudged),
        superseded=_cards_with(traces, Superseded),
        unfitted=_cards_with(traces, Unfitted),
        judged=bases.count("against_brief"),
        awaiting=bases.count("awaiting_confirmation"),
        no_brief=bases.count("no_brief"),
        numbers=len(numbers),
        resolved=sum(isinstance(outcome, Resolved) for outcome in numbers),
        stale=sum(isinstance(outcome, Stale) for outcome in numbers),
        unresolved=sum(isinstance(outcome, Unresolved) for outcome in numbers),
        not_verified=sum(isinstance(outcome, NotVerified) for outcome in numbers),
        agent_checked=sum(isinstance(outcome, AgentCheckedNumber) for outcome in numbers),
    )


def _cards_with(traces: Sequence[CardTrace], kind: type[CardFailure]) -> int:
    return sum(any(isinstance(failure, kind) for failure in trace.failures) for trace in traces)


def exit_code(counts: Tally, *, require_judged: bool = False) -> int:
    failed = (
        counts.unreadable
        + counts.unbound
        + counts.unlinked
        + counts.incomplete
        + counts.unconfirmed
        + counts.misjudged
        + counts.superseded
        + counts.unfitted
        + counts.stale
        + counts.unresolved
    )
    if require_judged:
        failed += counts.awaiting + counts.no_brief
    return 1 if failed or not counts.cards or not counts.numbers else 0


@dataclass(frozen=True, slots=True)
class TracedCard:
    order: int
    trace: CardTrace
    outcomes: tuple[RequirementOutcome, ...]


@dataclass(frozen=True, slots=True)
class TracedStore:
    cards: tuple[TracedCard, ...]

    @property
    def traces(self) -> tuple[CardTrace, ...]:
        return tuple(one.trace for one in self.cards)

    @property
    def outcomes(self) -> tuple[RequirementOutcome, ...]:
        return tuple(outcome for one in self.cards for outcome in one.outcomes)


def trace_cards(cards: Sequence[str], root: Path, roots: Roots) -> TracedStore:
    """`cards` is the JSON text of each scorecard, in the order the session got them."""
    table = load_materials()
    return TracedStore(
        tuple(
            TracedCard(order, *_read(order, text, root, roots, table))
            for order, text in enumerate(cards)
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trace_store", description="Trace every number on every scorecard in a transcript."
    )
    parser.add_argument("transcripts", nargs="+", type=Path, help="claude_session.py transcripts")
    parser.add_argument("--root", type=Path, default=entry.VARIANTS_ROOT, help="the variant store")
    parser.add_argument(
        "--briefs-root", type=Path, default=HOME_ROOTS.briefs, help="the brief store cards name"
    )
    parser.add_argument(
        "--projects-root",
        type=Path,
        default=HOME_ROOTS.projects,
        help="the project store that holds the person's answers",
    )
    parser.add_argument("--steps", action="store_true", help="print the chain of every number")
    parser.add_argument(
        "--require-judged",
        action="store_true",
        help="fail a card awaiting confirmation or scored with no brief",
    )
    args = parser.parse_args(argv)
    cards = [text for path in args.transcripts for text in read_cards(path)]
    found = trace_cards(
        cards, args.root, Roots(briefs=args.briefs_root, projects=args.projects_root)
    )
    for trace in found.traces:
        _print(trace, args.steps)
    counts = tally(found.traces)
    tracking = track(found.outcomes)
    print(f"cards: {counts.cards}, numbers: {counts.numbers}")
    print(
        f"cards unreadable: {counts.unreadable}, unbound: {counts.unbound}, "
        f"incomplete: {counts.incomplete}, unlinked: {counts.unlinked}"
    )
    print(
        f"cards unconfirmed: {counts.unconfirmed}, misjudged: {counts.misjudged}, "
        f"superseded: {counts.superseded}, unfitted: {counts.unfitted}"
    )
    print(
        f"cards judged: {counts.judged}, awaiting confirmation: {counts.awaiting}, "
        f"no brief: {counts.no_brief}"
    )
    print(
        f"numbers resolved: {counts.resolved}, stale: {counts.stale}, "
        f"unresolved: {counts.unresolved}"
    )
    print(f"agent measurements: {counts.not_verified}, not verified")
    print(f"numbers of agent-written checks the person approved: {counts.agent_checked}")
    print(f"strict pass rate: {describe(tracking.strict_pass_rate)}")
    print(f"requirements covered by reviewed checks: {describe(tracking.reviewed_coverage)}")
    print(
        "requirements covered by agent-written checks the person approved: "
        f"{describe(tracking.agent_coverage)}"
    )
    print(
        "requirements decided on a load case the agent described, counted apart: "
        f"{describe(tracking.described_coverage)}"
    )
    for line in describe_apart(tracking):
        print(line)
    if not counts.cards:
        print("no scorecard in the transcripts")
    elif not counts.numbers:
        print("no number on any scorecard")
    return exit_code(counts, require_judged=args.require_judged)


def _read(
    order: int, text: str, root: Path, roots: Roots, table: MaterialsTable
) -> tuple[CardTrace, tuple[RequirementOutcome, ...]]:
    try:
        card = material.STORED.validate_json(text)
    except (ValidationError, pint.UndefinedUnitError, ZeroDivisionError) as error:
        return CardTrace(f"card {order + 1}", (Unreadable(str(error).splitlines()[0]),), ()), ()
    trace = trace_card(card, root, roots, _table_scored_against(card, roots, table), SPEC_BY_ID)
    return trace, outcomes_of(card)


def _table_scored_against(card: Scorecard, roots: Roots, git: MaterialsTable) -> MaterialsTable:
    if not isinstance(card.basis, AgainstBrief | AwaitingConfirmation):
        return git
    try:
        project = briefs.read_brief(roots, card.basis.brief_id).project
    except BriefRefused:
        return git
    named = table_named(git, roots.projects, project, card.table_version)
    return named if named is not None else project_table(git, roots.projects, project).table


def _print(trace: CardTrace, steps: bool) -> None:
    broken = [one for one in trace.numbers if isinstance(one.outcome, Stale | Unresolved)]
    failed = bool(trace.failures or broken)
    print(f"{'FAIL' if failed else 'ok  '} {trace.variant_id}: {len(trace.numbers)} numbers")
    for failure in trace.failures:
        print(f"     {type(failure).__name__.upper()} {failure.reason}")
    for one in trace.numbers if steps else broken:
        print(f"     {_line(one)}")


def _line(one: Traced) -> str:
    head = f"{one.label} = {one.value}"
    outcome = one.outcome
    if isinstance(outcome, Stale | Unresolved | NotVerified | AgentCheckedNumber):
        return f"{type(outcome).__name__.upper()} {head}: {outcome.reason}"
    chain = " -> ".join(_step(step) for step in outcome.steps)
    return f"{head} -> {chain}"


def _step(step: Step) -> str:
    match step:
        case CheckStep():
            return f"computed by check {step.check_id} at version {step.version[:12]}"
        case TableStep():
            return (
                f"table {step.material_key}.{step.field}, {step.source.title}, {step.source.page}"
            )
        case ResearchedStep():
            return (
                f"researched {step.material_key}.{step.field}, record {step.record}, "
                f"{step.source.url}: {step.source.quote!r}"
            )
        case BoundStep():
            return f"the {step.bound} bound the server accepts for a researched {step.field}"
        case ConfirmedStep():
            return (
                f"confirmed by a person: brief {step.brief_id}, answer "
                f"{step.decision_sha256[:12]}, requirement {step.requirement_id} "
                f"({step.statement})"
            )
        case _:
            assert_never(step)


if __name__ == "__main__":
    sys.exit(main())
