"""Run every brief in the private set through a headless session and trace what it stored.

    uv run python evals/briefs/run.py --briefs ~/cad-evals/briefs --out ~/cad-evals/runs/<stamp>
        [--model sonnet] [--jobs 3] [--only ID ...] [--timeout 1800] [--require-traced]

Per brief it starts a fresh session, with its own server HOME under `<out>/<id>/home` and the
scripted person (`human.py`) answering the confirmation page, then runs the tracer with
--require-judged over that HOME's stores. `<out>/<id>/result.json` is written last, so a rerun
with the same `--out` skips the briefs that finished and runs the rest from a fresh HOME. A brief
whose session failed is run again. `summary.md` and `summary.json` are rewritten from the result
files on every run. Briefs run in parallel, at most `--jobs` at once.

Keep `--out` and `--briefs` outside the repo: transcripts hold the brief text. Exit code 1 means a
session failed or a brief did not run; with `--require-traced`, also a brief that did not trace.
"""

import argparse
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

from brief_set import BriefInput, load_set, prompt_for
from friction import minutes_to_first_result, read_pages
from outcome import BriefResult, Friction, Trace, is_finished, read_results, write_result
from session import run_session
from summary import markdown, summarize
from tracefacts import trace_session

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
        trace = trace_session(home, directory / "transcript.json")
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--briefs", type=Path, required=True, help="the private brief set")
    parser.add_argument("--out", type=Path, required=True, help="where runs and summaries go")
    parser.add_argument("--model", default=MODEL, help="Claude Code model alias for each session")
    parser.add_argument("--jobs", type=int, default=JOBS, help="briefs to run at once")
    parser.add_argument("--only", nargs="+", default=[], help="run only these brief ids")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_S, help="seconds per session")
    parser.add_argument("--require-traced", action="store_true", help="exit 1 on an untraced brief")
    args = parser.parse_args(argv)
    briefs, skipped = load_set(args.briefs)
    unknown = sorted(set(args.only) - {one.id for one in briefs})
    if unknown:
        parser.error(f"not in the set: {', '.join(unknown)}")
    chosen = [one for one in briefs if not args.only or one.id in args.only]
    args.out.mkdir(parents=True, exist_ok=True)
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
