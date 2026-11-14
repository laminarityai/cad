"""Check that the scorecard and the bake-off grader agree on the same variants.

    uv run python evals/bakeoff/agree.py            # Claude Code builds and scores the 10 parts
    uv run python evals/bakeoff/agree.py --replay   # the 60 stored build123d attempts, no model

Geometry comes from build_variant and score_variant only. The model never computes a verdict:
this script reads the scorecard and the STEP that the server stored, and runs grade.py on that
STEP.
"""

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import cache, partial
from pathlib import Path
from typing import Any, Final, Protocol, cast

import yaml
from inputs import Attempt, as_result_contract, brief_prompt, read_session, stored_attempts

from cad.checks.container.extents import SORTED_NAMES
from cad.checks.result import CheckResult, StepMissing, Verdict
from cad.sandbox.outcome import Built
from cad.scorecard import score
from cad.variants import entry, store

HERE: Final = Path(__file__).resolve().parent
ROOT: Final = HERE.parents[1]
SESSION: Final = ROOT / ".claude/skills/verify/scripts/claude_session.py"
MATERIAL_KEY: Final = "prusament-pla"
MODEL: Final = "sonnet"
VOLUME_TOL_MM3: Final = 0.01
EXTENT_TOL_MM: Final = 0.002
INVALID_CATEGORIES: Final = frozenset({"no_output", "invalid_solid"})
UNSCORED: Final = "unscored"
NOT_GRADED: Final = "not graded"
FLOAT_SLACK: Final = 1e-9
type Extents = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class CardSide:
    """What the scorecard says about one variant. `closed_solid` is the check's verdict, or
    `unscored` when no scorecard exists. The volume is the mass check's, and the extents are the
    sorted extents of the extents check. Both are None unless `closed_solid` passes and the check
    measured them."""

    closed_solid: str
    volume_mm3: float | None
    extents_mm: Extents | None


@dataclass(frozen=True, slots=True)
class GraderSide:
    """What grade.py says about the STEP the scorecard names: its category, and the volume and
    sorted extents it measured, which it reports for every valid solid."""

    category: str
    volume_mm3: float | None
    extents_mm: Extents | None


@dataclass(frozen=True, slots=True)
class Agreement:
    """`graded` is False for a row grade.py could not read, because the scorecard keeps no STEP.
    Such a row neither agrees nor disagrees, and the tally leaves it out."""

    agrees: bool
    reasons: tuple[str, ...]
    graded: bool = True


def within(a: float, b: float, tolerance: float) -> bool:
    return abs(a - b) <= tolerance + FLOAT_SLACK


@dataclass(frozen=True, slots=True)
class Row:
    label: str
    variant_id: str | None
    card: CardSide
    grader: GraderSide
    agreement: Agreement
    seconds: float
    cost_usd: float | None = None
    tool_calls: tuple[str, ...] = ()


def agree_rule(card: CardSide, grader: GraderSide) -> Agreement:
    """The scorecard and grade.py agree when `closed_solid` passes exactly when grade.py's
    category is not `no_output` or `invalid_solid`. When both call the solid valid, the volumes
    must differ by at most 0.01 mm3 and each sorted extent by at most 0.002 mm. A scorecard
    whose `closed_solid` is `unknown`, because the checks did not finish, never agrees."""
    if card.closed_solid == UNSCORED:
        return Agreement(False, ("no scorecard: the variant was not built or not scored",))
    if card.closed_solid == Verdict.UNKNOWN:
        return Agreement(False, ("the checks did not finish (closed_solid is unknown)",))
    card_valid = card.closed_solid == Verdict.PASS
    grader_valid = grader.category not in INVALID_CATEGORIES
    if card_valid != grader_valid:
        return Agreement(
            False, (f"closed_solid is {card.closed_solid} but grade.py says {grader.category}",)
        )
    if not card_valid:
        return Agreement(True, ())
    reasons: list[str] = []
    if card.volume_mm3 is None or grader.volume_mm3 is None:
        reasons.append(f"volume missing: scorecard {card.volume_mm3}, grade.py {grader.volume_mm3}")
    elif not within(card.volume_mm3, grader.volume_mm3, VOLUME_TOL_MM3):
        reasons.append(f"volume {card.volume_mm3} vs {grader.volume_mm3} mm3")
    if card.extents_mm is None or grader.extents_mm is None:
        reasons.append(
            f"extents missing: scorecard {card.extents_mm}, grade.py {grader.extents_mm}"
        )
    elif not all(
        within(a, b, EXTENT_TOL_MM) for a, b in zip(card.extents_mm, grader.extents_mm, strict=True)
    ):
        reasons.append(f"extents {card.extents_mm} vs {grader.extents_mm} mm")
    return Agreement(not reasons, tuple(reasons))


class Grade(Protocol):
    def grade(self, part_id: str, step_path: Path) -> dict[str, Any]: ...


@cache
def grader() -> Grade:
    spec = importlib.util.spec_from_file_location("bakeoff_grade", HERE / "grade.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Grade, cast(object, module))


class Driver(Protocol):
    def failure_of(self, stdout: str, stderr: str) -> str: ...


def _driver() -> Driver:
    """The session driver, loaded once by path and shared, as it is a script and not a package."""
    if "claude_session" not in sys.modules:
        spec = importlib.util.spec_from_file_location("claude_session", SESSION)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules["claude_session"] = module
    return cast(Driver, cast(object, sys.modules["claude_session"]))


def grader_side(part: str, step: Path) -> GraderSide:
    graded = grader().grade(part, step)
    measured: dict[str, Any] = graded.get("measured") or {}
    extents = measured.get("extents")
    return GraderSide(
        category=graded["category"],
        volume_mm3=measured.get("volume"),
        extents_mm=None if extents is None else cast(Extents, tuple(extents)),
    )


class EvidenceError(Exception):
    pass


class StepNotKept(Exception):
    def __init__(self, card: "CardSide", reason: str) -> None:
        super().__init__(reason)
        self.card = card


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def card_side(root: Path, variant_id: str) -> CardSide:
    """Raises EvidenceError when the stored files are not the ones the scorecard names, and
    StepNotKept, with the card's verdict alone, when the scorecard keeps no STEP for grade.py."""
    directory = root / variant_id
    try:
        card = score.peek_variant(variant_id, MATERIAL_KEY, root)
    except score.NotScored:
        return CardSide(UNSCORED, None, None)
    except entry.VariantRefused as error:
        raise EvidenceError(str(error)) from error
    verdict = next(r for r in card.finished if r.check_id == "closed_solid").verdict
    if card.brep_sha256 != sha256_of(directory / entry.BREP):
        raise EvidenceError("result.brep is not the BREP the scorecard measured")
    if isinstance(card.step, StepMissing):
        side = CardSide(verdict.value, None, None)
        raise StepNotKept(side, f"the scorecard keeps no STEP: {card.step.reason}")
    if card.step.sha256 != sha256_of(directory / entry.STEP):
        raise EvidenceError("result.step is not the STEP the scorecard names")
    if verdict != Verdict.PASS:
        return CardSide(verdict.value, None, None)
    mass = next(r for r in card.finished if r.check_id == "mass")
    extents = next(r for r in card.finished if r.check_id == "extents")
    return CardSide(verdict.value, mass.number("volume", "mm^3"), sorted_extents(extents))


def sorted_extents(result: CheckResult) -> Extents | None:
    if result.verdict != Verdict.PASS:
        return None
    return cast(
        Extents,
        tuple(result.number(f"sorted_extent:{name}", "mm") for name in SORTED_NAMES),
    )


def evaluate(label: str, part: str, variant_id: str | None, root: Path, seconds: float) -> Row:
    unscored = CardSide(UNSCORED, None, None)
    ungraded = GraderSide(NOT_GRADED, None, None)
    if variant_id is None:
        no_variant = Agreement(False, ("no variant was scored",))
        return Row(label, None, unscored, ungraded, no_variant, seconds)
    directory = root / variant_id
    try:
        card = card_side(root, variant_id)
    except StepNotKept as kept:
        alone = Agreement(False, (str(kept),), graded=False)
        return Row(label, variant_id, kept.card, ungraded, alone, seconds)
    except EvidenceError as error:
        evidence = Agreement(False, (str(error),))
        return Row(label, variant_id, unscored, ungraded, evidence, seconds)
    graded = grader_side(part, directory / entry.STEP)
    return Row(label, variant_id, card, graded, agree_rule(card, graded), seconds)


def replay_one(attempt: Attempt, root: Path) -> Row:
    started = time.monotonic()
    built = store.build_variant(as_result_contract(attempt.path.read_text()), root)
    if isinstance(built.outcome, Built):
        score.score_variant(built.variant_id, MATERIAL_KEY, root)
    return evaluate(attempt.label, attempt.part, built.variant_id, root, time.monotonic() - started)


def session_failure(stdout: str, stderr: str) -> str:
    """Why the session driver exited 1, read by the driver's own rule."""
    return _driver().failure_of(stdout, stderr)


def live_one(part: str, brief: str, out: Path, model: str) -> Row:
    started = time.monotonic()
    transcript = out / f"{part}.json"
    home = out / f"{part}-home"
    command = [
        sys.executable,
        str(SESSION),
        "--model",
        model,
        "--home",
        str(home),
        brief_prompt(brief, MATERIAL_KEY),
        str(transcript),
    ]
    done = subprocess.run(command, capture_output=True, text=True, check=False, cwd=ROOT)
    events: list[dict[str, Any]] = (
        json.loads(transcript.read_text()) if transcript.is_file() else []
    )
    session = read_session(events)
    row = evaluate(
        part, part, session.scored_variant, home / ".cad" / "variants", time.monotonic() - started
    )
    if done.returncode != 0:
        failure = session_failure(done.stdout, done.stderr)
        reasons = (*row.agreement.reasons, f"the session failed: {failure}")
        row = replace(row, agreement=Agreement(False, reasons))
    return replace(row, cost_usd=session.cost_usd, tool_calls=session.tool_calls)


HEADERS: Final = (
    "Run",
    "closed_solid",
    "Scorecard volume (mm3)",
    "Scorecard extents (mm)",
    "grade.py category",
    "grade.py volume (mm3)",
    "grade.py extents (mm)",
    "Verdict",
)


def cells(row: Row) -> list[str]:
    def volume(value: float | None) -> str:
        return "-" if value is None else f"{value:.2f}"

    def box(extents: Extents | None) -> str:
        return "-" if extents is None else " x ".join(f"{e:.3f}" for e in extents)

    return [
        row.label,
        row.card.closed_solid,
        volume(row.card.volume_mm3),
        box(row.card.extents_mm),
        row.grader.category,
        volume(row.grader.volume_mm3),
        box(row.grader.extents_mm),
        verdict_of(row.agreement),
    ]


def verdict_of(agreement: Agreement) -> str:
    if not agreement.graded:
        return NOT_GRADED
    return "agree" if agreement.agrees else "DISAGREE"


def format_row(row: Row) -> str:
    cost = "" if row.cost_usd is None else f", ${row.cost_usd:.3f}"
    why = "".join(f"\n    {reason}" for reason in row.agreement.reasons)
    return f"{' | '.join(cells(row))} ({row.seconds:.0f}s{cost}){why}"


def markdown(rows: list[Row]) -> str:
    lines = [f"| {' | '.join(HEADERS)} |", f"|{'---|' * len(HEADERS)}"]
    lines += [f"| {' | '.join(cells(row))} |" for row in rows]
    return "\n".join(lines) + "\n"


def selected(only: str, label: str) -> bool:
    return not only or f"/{only}/" in f"/{label}/"


def call(one: Callable[[], Row]) -> Row:
    return one()


def run_all(jobs: int, work: list[Callable[[], Row]]) -> list[Row]:
    rows: list[Row] = []
    with ThreadPoolExecutor(jobs) as pool:
        for row in pool.map(call, work):
            print(format_row(row), flush=True)
            rows.append(row)
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", action="store_true", help="grade the stored attempts")
    parser.add_argument("--attempt", type=int, help="replay attempt N, not each run's final one")
    parser.add_argument(
        "--only", default="", help="keep the rows whose label has this /-separated part"
    )
    parser.add_argument("--model", default=MODEL, help="Claude Code model alias for a live run")
    parser.add_argument("--jobs", type=int, default=1, help="rows to run at once")
    parser.add_argument("--out", type=Path, help="directory for the live transcripts")
    parser.add_argument("--markdown", type=Path, help="write the rows as a Markdown table")
    args = parser.parse_args(argv)
    work: list[Callable[[], Row]] = []
    root: Path | None = None
    if args.replay:
        root = Path(tempfile.mkdtemp(prefix="agree-store-"))
        for attempt in stored_attempts(args.attempt):
            if selected(args.only, attempt.label):
                work.append(partial(replay_one, attempt, root))
    else:
        out = args.out or Path(tempfile.mkdtemp(prefix="agree-live-"))
        out.mkdir(parents=True, exist_ok=True)
        print(f"transcripts: {out}", flush=True)
        for brief in yaml.safe_load((HERE / "prompts.yaml").read_text()):
            if selected(args.only, brief["id"]):
                work.append(partial(live_one, brief["id"], brief["prompt"], out, args.model))
    rows = run_all(args.jobs, work)
    if root:
        shutil.rmtree(root, ignore_errors=True)
    if not args.replay:
        print(f"cost: ${sum(row.cost_usd or 0.0 for row in rows):.3f}")
    if args.markdown:
        args.markdown.write_text(markdown(rows))
    said, passed = tally(rows)
    print(said)
    return 0 if passed else 1


def tally(rows: list[Row]) -> tuple[str, bool]:
    """The agreement count over the graded rows, and whether every row agrees. A row grade.py
    could not read is counted apart, and the run does not pass while one is left."""
    graded = [row for row in rows if row.agreement.graded]
    agreed = sum(row.agreement.agrees for row in graded)
    left = len(rows) - len(graded)
    said = f"{agreed}/{len(graded)} agree" + (f", {left} not graded" if left else "")
    return said, bool(graded) and agreed == len(graded) and not left


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
