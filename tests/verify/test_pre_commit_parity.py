import shlex
from collections.abc import Mapping
from pathlib import Path

from cad.verify.steps import STEPS

PRE_COMMIT_CONFIG = Path(__file__).resolve().parents[2] / ".pre-commit-config.yaml"

NOT_RUN_AT_COMMIT: Mapping[str, str] = {}

VERIFY_ONLY = ["uv", "run", "verify", "--only"]


def hook_step_names() -> list[str]:
    names: list[str] = []
    for line in PRE_COMMIT_CONFIG.read_text().splitlines():
        key, _, value = line.strip().partition(":")
        if key != "entry":
            continue
        words = shlex.split(value)
        assert words[: len(VERIFY_ONLY)] == VERIFY_ONLY, f"hook entry: {value}"
        assert len(words) == len(VERIFY_ONLY) + 1, f"hook entry: {value}"
        names.append(words[-1])
    return names


def test_pre_commit_runs_every_verify_step_once() -> None:
    expected = sorted(step.name for step in STEPS if step.name not in NOT_RUN_AT_COMMIT)
    assert sorted(hook_step_names()) == expected


def test_exclusions_name_real_steps() -> None:
    assert {step.name for step in STEPS} >= NOT_RUN_AT_COMMIT.keys()
