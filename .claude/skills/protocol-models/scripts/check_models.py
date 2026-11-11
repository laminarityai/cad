"""Model-check every protocol model with TLC and say whether each result is the expected one.

    check_models.py [--trace] [NAME ...]    run the named checks, or all of them
    check_models.py --mutants [NAME ...]    run the named mutants, or all of them
    check_models.py --changed-since REF     exit 1 when no model or covered file changed since REF

A check passes when TLC finds no error, or, for a check that records a known finding, when TLC
finds exactly that violation again. It prints TLC's counterexample on an unexpected result, and
on every result with --trace. A mutant writes one code regression into a scratch copy of a model,
and the check must catch it.

Under pre-commit (which sets PRE_COMMIT=1) a bare run checks nothing when --changed-since HEAD
finds nothing, so the hook's file filter is the coverage block itself and cannot drift from it.
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
from pathlib import Path
from typing import Final

from targets import CHECKS, MUTANTS, Check, Mutant

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
    r"^Error: (?:Invariant (\w+) is violated|Action property (\w+) is violated"
    r"|(Temporal) properties were violated|(Deadlock) )",
    re.MULTILINE,
)
STATES: Final = re.compile(r"([\d,]+) distinct states found")
DOWNLOAD_WAITS: Final = (2, 8, None)
"""Seconds to wait after each failed download before the next try; None means give up."""


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


def coverage() -> tuple[str, list[str]]:
    """The sync commit and the code files the models cover, from SKILL.md's coverage block."""
    block = re.search(r"```coverage\n(.*?)```", (SKILL / "SKILL.md").read_text(), re.DOTALL)
    if block is None:
        raise SystemExit("SKILL.md has no coverage block")
    lines = [line.split() for line in block.group(1).splitlines() if line.strip()]
    sync = next(words[1] for words in lines if words[0] == "sync:")
    files = [path for words in lines if words[0] != "sync:" for path in words[1:]]
    return sync, files


def changed_since(ref: str) -> list[str]:
    """The files that decide a TLC result, or that a model covers, changed since ref."""
    _, files = coverage()
    return subprocess.run(
        ["git", "diff", "--name-only", ref, "--", str(SKILL.relative_to(REPO)), *files],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip


def drift() -> None:
    """Warn when the code a model covers changed after the commit the skill last synced to."""
    sync, files = coverage()
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
    parser.add_argument(
        "--changed-since",
        metavar="REF",
        help="run nothing; list the model and covered files changed since REF, exit 1 if none",
    )
    args = parser.parse_args(argv)
    if args.changed_since is not None:
        ref = str(args.changed_since)
        changed = changed_since(ref)
        print("\n".join(changed) or f"nothing the models read or cover changed since {ref}")
        return 0 if changed else 1
    names: list[str] = args.names
    if (
        os.environ.get("PRE_COMMIT")
        and not names
        and not args.mutants
        and not changed_since("HEAD")
    ):
        print("nothing the models read or cover is in this commit, so TLC did not run")
        return 0
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
