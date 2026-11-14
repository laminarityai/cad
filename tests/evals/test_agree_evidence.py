import os
import subprocess
import sys
from pathlib import Path

import agree
import pytest

from cad.checks.result import StepMissing
from cad.scorecard.model import Scorecard
from tests.support.cards import VARIANT_ID, genuine_card

ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / ".claude/skills/verify/scripts/claude_session.py"
TRANSCRIPTS = ROOT / "tests/verify/transcripts"


def test_a_stored_step_the_scorecard_marks_missing_is_not_graded(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = genuine_card(step=StepMissing(reason="the STEP did not fit the report"))

    def peek(variant_id: str, material_key: str, root: Path) -> Scorecard:
        del variant_id, material_key, root
        return card

    def grade(part: str, step: Path) -> agree.GraderSide:
        raise AssertionError(f"graded {step}")

    monkeypatch.setattr(agree.score, "peek_variant", peek)
    monkeypatch.setattr(agree, "grader_side", grade)
    row = agree.evaluate("plate", "plate", VARIANT_ID, store, 0.0)
    assert row.grader.category == "not graded"
    assert not row.agreement.agrees
    assert row.agreement.reasons == (
        "the scorecard keeps no STEP: the STEP did not fit the report",
    )
    assert row.card.closed_solid == "pass"
    assert agree.cells(row)[-1] == "not graded"
    agreed = agree.Row("bracket", VARIANT_ID, row.card, row.grader, agree.Agreement(True, ()), 0.0)
    assert agree.tally([row, agreed]) == ("1/1 agree, 1 not graded", True)
    assert agree.tally([row]) == ("0/0 agree, 1 not graded", False)


def drive(transcript: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    stub = tmp_path / "bin" / "claude"
    stub.parent.mkdir()
    stub.write_text(f"#!/bin/sh\ncat {TRANSCRIPTS / transcript}\n")
    stub.chmod(0o755)
    return subprocess.run(
        [sys.executable, str(SESSION), "a prompt", str(tmp_path / "out.json")],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{stub.parent}{os.pathsep}{os.environ['PATH']}"},
    )


def test_a_failed_session_is_blamed_on_the_drivers_check_not_the_reply(tmp_path: Path) -> None:
    done = drive("bash_reachable.json", tmp_path)
    assert done.returncode == 1
    assert agree.session_failure(done.stdout, done.stderr) == "tools available outside cad: Bash"


def test_a_driver_that_raised_is_blamed_on_its_traceback() -> None:
    stdout = "server home: /tmp/h\ninit: cad connected\n"
    stderr = "Traceback (most recent call last):\n  File ...\nStopIteration\n"
    assert agree.session_failure(stdout, stderr) == "StopIteration"


def test_a_session_that_reported_an_error_says_so() -> None:
    stdout = "server home: /tmp/h\ninit: cad connected\nresult: I could not finish.\n"
    assert agree.session_failure(stdout, "") == "the session reported an error"
