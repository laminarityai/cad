"""Run every brief in the private set through a headless session and trace what it stored.

    uv run python evals/briefs/run.py --briefs ~/cad-evals/briefs --out ~/cad-evals/runs/<stamp>
        [--model sonnet] [--jobs 3] [--only ID ...] [--timeout 1800] [--require-traced]
    uv run python evals/briefs/run.py --driver inprocess --briefs ~/cad-evals/briefs --out <dir>
        [--model scripted|<anthropic model id>] [--only ID ...] [--opener PROGRAM] [--timeout S]

Per brief it starts a fresh session, with its own server HOME under `<out>/<id>/home` and the
scripted person (`human.py`) answering the confirmation page, then runs the tracer with
--require-judged over that HOME's stores. `<out>/<id>/result.json` is written last, so a rerun
with the same `--out` skips the briefs that finished and runs the rest from a fresh HOME. A brief
whose session failed is run again. `summary.md` and `summary.json` are rewritten from the result
files on every run. Briefs run in parallel, at most `--jobs` at once.

The `inprocess` driver runs the chat agent in this process and stops at the Auto stop. See
`inprocess.py`.

Keep `--out` and `--briefs` outside the repo: transcripts hold the brief text. Exit code 1 means a
session failed or a brief did not run; with `--require-traced`, also a brief that did not trace.
"""

import argparse
import json
import os
import shutil
import stat
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Final

from autoresult import AutoResult
from brief_set import BriefInput, load_set, prompt_for
from friction import minutes_to_first_result, read_pages
from inprocess import SCRIPTED, MissingKey, require_key, run_set
from outcome import BriefResult, Friction, Trace, is_finished, read_results, write_result
from session import run_session
from summary import markdown, summarize
from tracefacts import failed_trace, trace_session

from cad.chat.key_file import load_key

MODEL: Final = "sonnet"
JOBS: Final = 3
TIMEOUT_S: Final = 1800.0


def _remove_read_only(remove: Callable[[str], object], path: str, _error: BaseException) -> None:
    os.chmod(Path(path).parent, stat.S_IRWXU)
    os.chmod(path, stat.S_IRWXU)
    remove(path)


def run_one(brief: BriefInput, out: Path, model: str, timeout_s: float) -> BriefResult:
    directory = out / brief.id
    if directory.exists():
        shutil.rmtree(directory, onexc=_remove_read_only)
    home = directory / "home"
    home.mkdir(parents=True)
    human_log = directory / "human.jsonl"
    started = time.monotonic()
    session = run_session(
        prompt_for(brief), home, directory / "transcript.json", human_log, model, timeout_s
    )
    seconds = time.monotonic() - started
    pages = read_pages(human_log)
    stores = home / ".cad"
    friction = Friction(
        confirmation_pages=pages.shown,
        ask_calls=session.facts.ask_calls,
        minutes_to_first_result=minutes_to_first_result(
            stores / "briefs", stores / "variants", seconds
        ),
    )
    failed = session.timed_out or session.exit_code != 0 or session.facts.is_error
    trace: Trace | None = None
    note: str | None = None
    if session.timed_out:
        note = f"timed out after {timeout_s:.0f}s"
    elif failed:
        note = session.note
    else:
        trace = _trace(home, directory / "transcript.json")
    if pages.errors:
        note = "; ".join(filter(None, [note, *pages.errors]))
    return BriefResult(
        id=brief.id,
        domain=brief.domain,
        status="session_failed" if failed else "finished",
        model=session.facts.model,
        cost_usd=session.facts.cost_usd,
        turns=session.facts.turns,
        seconds=seconds,
        note=note,
        trace=trace,
        friction=friction,
    )


def _trace(home: Path, transcript: Path) -> Trace:
    """A bug in the tracer fails this brief's trace, and the other briefs still run."""
    try:
        return trace_session(home, transcript)
    except Exception as error:
        return failed_trace(error)


def run_and_report(brief: BriefInput, out: Path, model: str, timeout_s: float) -> BriefResult:
    result = run_one(brief, out, model, timeout_s)
    write_result(out, result)
    trace = result.trace
    state = (
        result.status
        if trace is None
        else ("traced" if trace.traced else f"not traced ({len(trace.untraced)} untraced)")
    )
    print(f"{brief.id}: {state}, {result.seconds:.0f}s", flush=True)
    return result


def run_inprocess(args: argparse.Namespace, chosen: list[BriefInput]) -> int:
    results: list[AutoResult] = run_set(chosen, args.out, args.model, args.opener, args.timeout)
    rows = [one.model_dump(mode="json") for one in results]
    (args.out / "auto-summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    passed = sum(one.passed for one in results)
    print(f"{passed} of {len(results)} briefs passed in the in-process driver")
    return 0 if passed == len(results) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--briefs", type=Path, required=True, help="the private brief set")
    parser.add_argument("--out", type=Path, required=True, help="where runs and summaries go")
    parser.add_argument(
        "--driver",
        choices=("session", "inprocess"),
        default="session",
        help="a headless Claude Code session per brief, or the in-process chat agent",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"session: a Claude Code alias (default {MODEL}). inprocess: {SCRIPTED}, the "
        f"default, or an Anthropic model id",
    )
    parser.add_argument(
        "--opener", default=None, help="inprocess: a program to open the confirmation page"
    )
    parser.add_argument("--jobs", type=int, default=JOBS, help="briefs to run at once")
    parser.add_argument("--only", nargs="+", default=[], help="run only these brief ids")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_S, help="seconds per session")
    parser.add_argument("--require-traced", action="store_true", help="exit 1 on an untraced brief")
    args = parser.parse_args(argv)
    inprocess = args.driver == "inprocess"
    args.model = args.model or (SCRIPTED if inprocess else MODEL)
    if inprocess:
        if args.model != SCRIPTED:
            load_key(os.environ)
        try:
            require_key(args.model, os.environ)
        except MissingKey as missing:
            print(missing, file=sys.stderr)
            return 1
    briefs, skipped = load_set(args.briefs)
    unknown = sorted(set(args.only) - {one.id for one in briefs})
    if unknown:
        parser.error(f"not in the set: {', '.join(unknown)}")
    chosen = [one for one in briefs if not args.only or one.id in args.only]
    args.out.mkdir(parents=True, exist_ok=True)
    if inprocess:
        return run_inprocess(args, chosen)
    pending = [one for one in chosen if not is_finished(args.out, one.id)]
    print(
        f"{len(chosen)} briefs, {len(chosen) - len(pending)} already finished, running "
        f"{len(pending)} on {args.model} with {args.jobs} at once; not briefs: {skipped}",
        flush=True,
    )
    with ThreadPoolExecutor(args.jobs) as pool:
        list(
            pool.map(
                partial(run_and_report, out=args.out, model=args.model, timeout_s=args.timeout),
                pending,
            )
        )
    ids = [one.id for one in chosen]
    results = read_results(args.out, ids)
    missing = [one for one in ids if one not in {r.id for r in results}]
    summary = summarize(results, missing, args.model)
    text = markdown(summary, missing)
    (args.out / "summary.md").write_text(text)
    (args.out / "summary.json").write_text(summary.model_dump_json(indent=2) + "\n")
    print(text)
    failed = bool(missing) or any(one.status != "finished" for one in results)
    untraced = any(one.trace is None or not one.trace.traced for one in results)
    return 1 if failed or (args.require_traced and untraced) else 0


if __name__ == "__main__":
    sys.exit(main())
