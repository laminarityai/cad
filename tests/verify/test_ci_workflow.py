import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import yaml

from cad.verify.steps import STEPS

ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
VERIFY = ["uv", "run", "--locked", "verify"]


def jobs() -> dict[str, dict[str, Any]]:
    return cast("dict[str, dict[str, Any]]", yaml.safe_load(CI_WORKFLOW.read_text())["jobs"])


def uv_commands() -> list[list[str]]:
    runs = (step.get("run", "") for job in jobs().values() for step in job["steps"])
    return [words for words in map(shlex.split, runs) if words[:1] == ["uv"]]


def test_ci_installs_and_runs_from_the_committed_lockfile() -> None:
    assert uv_commands()
    for words in uv_commands():
        assert words[:2] in (["uv", "sync"], ["uv", "run"]), words
        assert words[2] == "--locked", words


def test_ci_runs_every_verify_step() -> None:
    ran: list[str] = []
    for words in uv_commands():
        if words[: len(VERIFY)] == VERIFY:
            rest = words[len(VERIFY) :]
            assert rest[::2] == ["--only"] * len(rest[1::2]), words
            ran += rest[1::2] or [step.name for step in STEPS]
    assert sorted(ran) == sorted(step.name for step in STEPS)


def test_the_test_jobs_cover_every_shard() -> None:
    tests = jobs()["tests"]
    shards: list[int] = tests["strategy"]["matrix"]["shard"]
    assert tests["env"]["CAD_TEST_SHARD"] == f"${{{{ matrix.shard }}}}/{len(shards)}"
    assert shards == list(range(1, len(shards) + 1))


def collected(shard: str | None) -> set[str]:
    env = {key: value for key, value in os.environ.items() if key != "CAD_TEST_SHARD"}
    if shard is not None:
        env["CAD_TEST_SHARD"] = shard
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:xdist", "tests/verify"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    return {line for line in done.stdout.splitlines() if "::" in line}


def test_the_shards_split_the_tests_by_file_with_none_lost_or_doubled() -> None:
    everything = collected(None)
    parts = [collected(f"{index}/3") for index in (1, 2, 3)]
    assert sum(map(len, parts)) == len(everything)
    assert set().union(*parts) == everything
    files = [{test.split("::")[0] for test in part} for part in parts]
    assert all(not (a & b) for i, a in enumerate(files) for b in files[i + 1 :])
