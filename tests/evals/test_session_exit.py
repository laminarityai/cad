"""The harness reads a session's stores only after every process the session started has exited,
so a check record the cad server writes after Claude Code exits is read, not missed."""

import subprocess
from pathlib import Path

import pytest
import run
import session
from brief_set import BriefInput
from outcome import read_results
from session import StillAlive, run_session

LATE_WRITER = """
import subprocess, sys
from pathlib import Path
home, transcript = Path(sys.argv[-3]), Path(sys.argv[-1])
late = (
    "import sys, time; from pathlib import Path; time.sleep(1); "
    "Path(sys.argv[1]).write_text('stored')"
)
subprocess.Popen(
    [sys.executable, "-c", late, str(home / "record")],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
transcript.write_text("[]")
"""


def test_a_record_stored_after_claude_exits_lands_before_the_stores_are_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "claude_session.py"
    fake.write_text(LATE_WRITER)
    monkeypatch.setattr(session, "SESSION", fake)
    home = tmp_path / "home"
    home.mkdir()
    run_session("a brief", home, tmp_path / "transcript.json", tmp_path / "human.jsonl", "m", 30)
    assert (home / "record").read_text() == "stored"


def test_a_process_left_in_the_group_after_the_wait_is_killed(tmp_path: Path) -> None:
    leader = subprocess.Popen(
        ["sh", "-c", "sleep 60 >/dev/null 2>&1 & exit 0"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    leader.wait()
    assert session.alive(leader.pid)
    session.wait_for_group(leader.pid, exit_s=0.2, kill_s=5)
    assert not session.alive(leader.pid)


def test_a_group_that_survives_the_kill_is_an_error_and_not_an_endless_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    killed: list[int] = []

    def kill(_group: int, sig: int) -> None:
        killed.append(sig)

    def alive(_group: int) -> bool:
        return True

    monkeypatch.setattr(session, "alive", alive)
    monkeypatch.setattr(session.os, "killpg", kill)
    with pytest.raises(StillAlive, match=r"still alive 0\.3 s after SIGKILL"):
        session.wait_for_group(4242, exit_s=0.1, kill_s=0.3)
    assert killed


FINISHED = """
import json, sys, time
from pathlib import Path
time.sleep(float(sys.argv[-2]))
Path(sys.argv[-1]).write_text(json.dumps([{"type": "result", "is_error": False}]))
"""
STUCK = "process group 42 was still alive 5 s after SIGKILL"


def run_briefs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sleeps: dict[str, float], *timeout: str
) -> int:
    """One brief at a time, each session sleeps the seconds its brief names, and the last
    brief's session leaves a process that will not die."""
    fake = tmp_path / "claude_session.py"
    fake.write_text(FINISHED)
    monkeypatch.setattr(session, "SESSION", fake)

    def prompt(brief: BriefInput) -> str:
        return str(sleeps[brief.id])

    monkeypatch.setattr(run, "prompt_for", prompt)
    waited = session.wait_for_group
    calls: list[int] = []

    def wait(group: int) -> None:
        waited(group)
        calls.append(group)
        if len(calls) == len(sleeps):
            raise StillAlive(STUCK)

    monkeypatch.setattr(session, "wait_for_group", wait)
    briefs = tmp_path / "set"
    briefs.mkdir()
    for name in sleeps:
        (briefs / f"{name}.yaml").write_text(f"id: {name}\ndomain: tests\nbrief: x\n")
    out = ["--out", str(tmp_path / "out"), "--jobs", "1"]
    return run.main(["--briefs", str(briefs), *out, *timeout])


def test_a_group_that_will_not_die_fails_its_brief_and_the_summary_is_still_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_briefs(tmp_path, monkeypatch, {"one": 0, "two": 0}) == 1
    out = tmp_path / "out"
    [one, two] = read_results(out, ["one", "two"])
    assert (one.status, two.status) == ("finished", "session_failed")
    assert two.note == STUCK
    assert (out / "summary.md").is_file()


def test_a_session_that_times_out_and_will_not_die_keeps_its_timed_out_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_briefs(tmp_path, monkeypatch, {"two": 30}, "--timeout", "1") == 1
    [two] = read_results(tmp_path / "out", ["two"])
    assert (two.status, two.note) == ("session_failed", f"timed out after 1s; {STUCK}")


def test_an_error_that_is_not_a_group_left_alive_is_not_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_group: int) -> None:
        raise RecursionError("a bug in the harness")

    fake = tmp_path / "claude_session.py"
    fake.write_text("")
    monkeypatch.setattr(session, "SESSION", fake)
    monkeypatch.setattr(session, "wait_for_group", broken)
    with pytest.raises(RecursionError):
        run_session("a brief", tmp_path, tmp_path / "t.json", tmp_path / "h.jsonl", "m", 30)
