"""Trace every number on every scorecard stored in a variant store.

    uv run python evals/briefs/trace_store.py                  # the store under ~/.cad/variants
    uv run python evals/briefs/trace_store.py --root DIR       # another store
    uv run python evals/briefs/trace_store.py --steps          # print each number's chain

Exits 1 when any number does not resolve, when a stored scorecard cannot be read, or when the store
holds no scorecard, because a pass over nothing proves nothing.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from provenance import CheckStep, TableStep, Traced, Unresolved, trace_card
from pydantic import ValidationError
from tracking import describe, outcomes_of, track

from cad.checks.report import SPECS
from cad.scorecard.model import Scorecard
from cad.scorecard.score import SCORECARD
from cad.tables.materials import load_materials
from cad.variants import entry

SPEC_BY_ID: Final = {spec.id: spec for spec in SPECS}


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
    broken = 0
    numbers = 0
    outcomes = []
    for path in paths:
        try:
            card = Scorecard.model_validate_json(path.read_text())
        except (OSError, ValidationError) as error:
            broken += 1
            print(f"UNREADABLE {path.parent.name}: {str(error).splitlines()[0]}")
            continue
        traced = trace_card(card, table, SPEC_BY_ID)
        failed = [one for one in traced if isinstance(one.outcome, Unresolved)]
        broken += len(failed)
        numbers += len(traced)
        outcomes.extend(outcomes_of(card))
        print(f"{'FAIL' if failed else 'ok  '} {card.variant_id}: {len(traced)} numbers")
        for one in traced if args.steps else failed:
            print(f"     {_line(one)}")
    tracking = track(tuple(outcomes))
    print(f"scorecards: {len(paths)}, numbers: {numbers}, unresolved or unreadable: {broken}")
    print(f"strict pass rate: {describe(tracking.strict_pass_rate)}")
    print(f"requirements covered by reviewed checks: {describe(tracking.reviewed_coverage)}")
    if not paths:
        print(f"no scorecard under {args.root}")
    return 1 if broken or not paths else 0


def _line(one: Traced) -> str:
    head = f"{one.check_id}.{one.name} = {one.value}"
    outcome = one.outcome
    if isinstance(outcome, Unresolved):
        return f"UNRESOLVED {head}: {outcome.reason}"
    chain = " -> ".join(_step(step) for step in outcome.steps)
    return f"{head} -> {chain}"


def _step(step: CheckStep | TableStep) -> str:
    if isinstance(step, CheckStep):
        return f"check {step.check_id} {step.version[:12]} cites {step.sources[0].title}"
    return f"table {step.material_key}.{step.field}, {step.source.title}, {step.source.page}"


if __name__ == "__main__":
    sys.exit(main())
