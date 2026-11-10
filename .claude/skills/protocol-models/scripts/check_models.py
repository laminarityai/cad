"""Model-check every protocol model with TLC and say whether each result is the expected one.

    check_models.py [--trace] [NAME ...]    run the named checks, or all of them
    check_models.py --mutants [NAME ...]    run the named mutants, or all of them

A check passes when TLC finds no error, or, for a check that records a known finding, when TLC
finds exactly that violation again. It prints TLC's counterexample on an unexpected result, and
on every result with --trace. A mutant writes one code regression into a scratch copy of a model,
and the check must catch it.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

SKILL: Final = Path(__file__).resolve().parents[1]
MODELS: Final = SKILL / "models"
REPO: Final = SKILL.parents[2]
TLA_VERSION: Final = "1.7.4"
JAR_URL: Final = (
    f"https://github.com/tlaplus/tlaplus/releases/download/v{TLA_VERSION}/tla2tools.jar"
)
JAR_SHA256: Final = "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"
PASSED: Final = "Model checking completed. No error has been found."
VIOLATION: Final = re.compile(
    r"^Error: (?:Invariant (\w+) is violated|(Temporal) properties were violated|(Deadlock) )",
    re.MULTILINE,
)
STATES: Final = re.compile(r"([\d,]+) distinct states found")
DOWNLOAD_WAITS: Final = (2, 8, None)
"""Seconds to wait after each failed download before the next try; None means give up."""


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    module: str
    config: str
    finding: str | None = None
    """The violation this check is known to find, named as TLC names it, or None to pass."""


JOB_LANES: Final = Check("JobLanes", "JobLanes.tla", "JobLanes.cfg")
JOB_LANES_CAP: Final = Check("JobLanesCap", "JobLanes.tla", "JobLanesCap.cfg")
ANSWERS: Final = Check("Answers", "Answers.tla", "Answers.cfg")
CHECKS: Final = (
    JOB_LANES,
    JOB_LANES_CAP,
    Check("JobLanesTwoServers", "JobLanes.tla", "JobLanesTwoServers.cfg"),
    Check(
        "JobLanesTwoServersRefusal",
        "JobLanes.tla",
        "JobLanesTwoServersRefusal.cfg",
        finding="InterruptedMeansInterrupted",
    ),
    Check("JobLanesPeek", "JobLanes.tla", "JobLanesPeek.cfg", finding="PeekMeansInterrupted"),
    ANSWERS,
    Check("AnswersStale", "Answers.tla", "AnswersStale.cfg", finding="StaleWritesNothing"),
)


@dataclass(frozen=True, slots=True)
class Mutant:
    name: str
    regression: str
    check: Check
    edits: tuple[tuple[str, str], ...]
    """(old, new) text replacements; each old text must occur exactly once in the model."""
    catches: str


MUTANTS: Final = (
    Mutant(
        "quick-skips-flying",
        "_take_off stops looking in _flying",
        JOB_LANES,
        (('IF flying[p]["quick"] # "none" THEN', "IF FALSE THEN"),),
        "OneContainerPerKey",
    ),
    Mutant(
        "read-skips-mac",
        "job_store.read stops verifying the MAC",
        JOB_LANES,
        (('Stored(j) == disk[j] = "honest"', 'Stored(j) == disk[j] # "none"'),),
        "NeverTrustForged",
    ),
    Mutant(
        "attempt-kept-on-failure",
        "end_attempt runs only after a stored result, not in _attempt's finally",
        JOB_LANES_CAP,
        (
            (
                "/\\ attempt' = [attempt EXCEPT ![wjob[p]] = 0]",
                '/\\ attempt\' = IF wres[p] = "ok" THEN [attempt EXCEPT ![wjob[p]] = 0] '
                "ELSE attempt",
            ),
        ),
        "InterruptedMeansInterrupted",
    ),
    Mutant(
        "worker-started-before-put",
        "_enqueue checks for a worker before it puts the job on the queue",
        JOB_LANES_CAP,
        (
            ("""= "startworker"]""", """= "quick"]"""),
            ("""= "enqueue"]""", """= "startworker"]"""),
            (
                """<<worker, wpc>>\n    /\\ cpc' = [cpc EXCEPT ![t] = "quick"]""",
                """<<worker, wpc>>\n    /\\ cpc' = [cpc EXCEPT ![t] = "enqueue"]""",
            ),
        ),
        "Temporal",
    ),
    Mutant(
        "no-cap-refusal",
        "_interrupted_too_often stops refusing fea at the attempt cap",
        JOB_LANES_CAP,
        (
            (
                'ELSE IF attempt["fea"] >= Cap THEN\n            /\\ cfea',
                "ELSE IF FALSE THEN\n            /\\ cfea",
            ),
        ),
        "CapStopsReruns",
    ),
    Mutant(
        "no-begin-attempt",
        "_attempt stops calling job_store.begin_attempt, so no crash is ever counted",
        JOB_LANES_CAP,
        (("/\\ attempt' = [attempt EXCEPT ![wjob[p]] = @ + 1]", "/\\ attempt' = attempt"),),
        "CapStopsReruns",
    ),
    Mutant(
        "dead-worker-kept",
        "_drain's finally leaves _worker set, the bug 0f22adb fixed",
        JOB_LANES_CAP,
        (("ELSE /\\ worker' = [worker EXCEPT ![p] = FALSE]", "ELSE /\\ worker' = worker"),),
        "Temporal",
    ),
    Mutant(
        "record-for-ignores-ledger",
        "append_answer's record_for stops refusing an item a stored answer lists",
        ANSWERS,
        (("/\\ IF Answered(q.rev)\n", "/\\ IF FALSE\n"),),
        "OneAnswerPerItem",
    ),
    Mutant(
        "publish-replaces",
        "signed.publish uses os.replace instead of os.link, so it overwrites a taken slot",
        ANSWERS,
        (
            ("/\\ Len(ledger) = q.seen\n", "/\\ Len(ledger) >= q.seen\n"),
            (
                "ledger' = Append(ledger, [rev |-> q.rev, page |-> q.page, by |-> q.by])",
                "ledger' = SubSeq(ledger, 1, q.seen)"
                " \\o <<[rev |-> q.rev, page |-> q.page, by |-> q.by]>>"
                " \\o SubSeq(ledger, q.seen + 2, Len(ledger))",
            ),
        ),
        "RecordedIsKept",
    ),
    Mutant(
        "no-changed-check",
        "answer_page stops returning Changed when the pending items no longer match the page",
        ANSWERS,
        (("IF Pending = {q.rev} THEN", "IF TRUE THEN"),),
        "ChangedWritesNothing",
    ),
    Mutant(
        "agent-answers",
        "verifier.person accepts an agent's access token, so the agent opens and posts the page",
        ANSWERS,
        (("Callers == Persons \\cup Others", "Callers == Persons \\cup Others \\cup Agents"),),
        "OnlyTenantPersonsAnswer",
    ),
    Mutant(
        "seal-ignores-session",
        "snapshot.seal stops binding the session, so another session's leaked form records",
        ANSWERS,
        (("/\\ q.by = pages[q.page].person\n", "/\\ TRUE\n"),),
        "AnsweredByTheOpener",
    ),
    Mutant(
        "snapshot-unbound",
        "answer_page drops its account check and the seal stops binding the session, so a form"
        " that leaked to another account records",
        ANSWERS,
        (
            (
                "IF /\\ Account(q.by) = Tenant\n          /\\ q.by = pages[q.page].person\n",
                "IF TRUE\n",
            ),
            # Another session of the tenant's account could also post the leaked form, which
            # breaks AnsweredByTheOpener at the same depth; masking it keeps the verdict stable.
            (
                "    \\A i \\in 1..Len(ledger) : ledger[i].by = pages[ledger[i].page].person\n",
                "    TRUE\n",
            ),
        ),
        "OnlyTenantPersonsAnswer",
    ),
)


def jar() -> Path:
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "cad"
    path = cache / f"tla2tools-{TLA_VERSION}.jar"
    if path.is_file() and _sha256(path.read_bytes()) == JAR_SHA256:
        return path
    data = _download(JAR_URL, path)
    if _sha256(data) != JAR_SHA256:
        raise SystemExit(f"{JAR_URL} does not have sha256 {JAR_SHA256}; not running it")
    cache.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}-{os.getpid()}")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    return path


def _download(url: str, path: Path) -> bytes:
    for wait in DOWNLOAD_WAITS:
        print(f"downloading TLA+ tools {TLA_VERSION} to {path}", flush=True)
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data: bytes = response.read()
        except OSError as error:
            if wait is None:
                raise SystemExit(f"cannot download {url}: {error}") from error
            print(f"download failed ({error}); retrying in {wait} s", flush=True)
            time.sleep(wait)
        else:
            return data
    raise AssertionError("DOWNLOAD_WAITS ends with None")


def java_or_none() -> str | None:
    """The java on PATH when it runs. macOS ships a /usr/bin/java stub that only fails."""
    java = shutil.which("java")
    if java is None:
        return None
    probe = subprocess.run([java, "-version"], capture_output=True, check=False)
    return java if probe.returncode == 0 else None


def tlc(check: Check, models: Path, tools: Path, java: str) -> tuple[str, float]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="tlc-") as states:
        done = subprocess.run(
            [java, "-XX:+UseParallelGC", "-cp", str(tools), "tlc2.TLC", "-workers", "auto",
             "-metadir", states, "-config", check.config, check.module],
            cwd=models, capture_output=True, text=True, check=False,
        )  # fmt: skip
    return done.stdout + done.stderr, time.monotonic() - started


def violations(output: str) -> list[str]:
    return [next(name for name in match.groups() if name) for match in VIOLATION.finditer(output)]


def run(check: Check, tools: Path, java: str, trace: bool) -> bool:
    output, seconds = tlc(check, MODELS, tools, java)
    found = violations(output)
    states = STATES.findall(output)
    size = f"{states[-1]} states" if states else "no state count"
    if check.finding is None and PASSED in output:
        print(f"PASS  {check.name}: {size}, {seconds:.1f} s")
    elif check.finding is not None and found == [check.finding]:
        print(f"PASS  {check.name}: finds the recorded {check.finding} again, {seconds:.1f} s")
    else:
        wanted = "no error" if check.finding is None else f"exactly {check.finding}"
        print(f"FAIL  {check.name}: wanted {wanted}, TLC found {found or 'no verdict'}\n{output}")
        return False
    if trace:
        print(output)
    return True


def mutate(mutant: Mutant, tools: Path, java: str, trace: bool) -> bool:
    with tempfile.TemporaryDirectory(prefix="mutant-") as scratch:
        models = Path(scratch)
        shutil.copytree(MODELS, models, dirs_exist_ok=True)
        spec = models / mutant.check.module
        text = spec.read_text()
        for old, new in mutant.edits:
            if text.count(old) != 1:
                print(f"STALE   {mutant.name}: the model no longer has exactly one {old!r}")
                return False
            text = text.replace(old, new)
        spec.write_text(text)
        output, seconds = tlc(mutant.check, models, tools, java)
    found = violations(output)
    caught = found == [mutant.catches]
    if caught:
        print(f"CAUGHT  {mutant.name}: {mutant.regression}; {mutant.catches}, {seconds:.1f} s")
    else:
        print(f"MISSED  {mutant.name}: wanted {mutant.catches}, TLC found {found or 'no error'}")
    if trace or not caught:
        print(output)
    return caught


def drift() -> None:
    """Warn when the code a model covers changed after the commit the skill last synced to."""
    block = re.search(r"```coverage\n(.*?)```", (SKILL / "SKILL.md").read_text(), re.DOTALL)
    if block is None:
        raise SystemExit("SKILL.md has no coverage block")
    lines = [line.split() for line in block.group(1).splitlines() if line.strip()]
    sync = next(words[1] for words in lines if words[0] == "sync:")
    files = [path for words in lines if words[0] != "sync:" for path in words[1:]]
    known = subprocess.run(
        ["git", "cat-file", "-e", f"{sync}^{{commit}}"], cwd=REPO, capture_output=True, check=False
    )
    if known.returncode != 0:
        print(f"note: sync commit {sync} is not in this clone, so drift was not checked")
        return
    changed = subprocess.run(
        ["git", "diff", "--name-only", sync, "--", *files],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    for path in changed:
        print(f"warning: {path} changed since sync commit {sync}; recheck the model against it")


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check_models.py", description="Model-check the protocol models with TLC."
    )
    parser.add_argument("names", nargs="*", help="checks (or with --mutants, mutants) to run")
    parser.add_argument("--mutants", action="store_true", help="run mutants instead of checks")
    parser.add_argument("--trace", action="store_true", help="print TLC's output for every run")
    args = parser.parse_args(argv)
    names: list[str] = args.names
    known = {one.name for one in (MUTANTS if args.mutants else CHECKS)}
    unknown = sorted(set(names) - known)
    if unknown:
        print(f"nothing is named {', '.join(unknown)}; the names are {', '.join(sorted(known))}")
        return 2
    java = java_or_none()
    if java is None:
        print(
            "no working java on PATH; TLC needs Java 11 or later. On macOS /usr/bin/java is a stub"
            " until a JDK is installed: brew install --cask temurin. On Debian or Ubuntu:"
            " apt install default-jre-headless."
        )
        return 1
    drift()
    tools = jar()
    if args.mutants:
        chosen = [one for one in MUTANTS if not names or one.name in names]
        return 0 if all([mutate(one, tools, java, args.trace) for one in chosen]) else 1
    checks = [one for one in CHECKS if not names or one.name in names]
    return 0 if all([run(one, tools, java, args.trace) for one in checks]) else 1


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
