"""The harness reads a session's stores only after every process the session started has exited,
so a check record the cad server writes after Claude Code exits is read, not missed."""

import subprocess
from pathlib import Path

import pytest
import session
from session import run_session

LATE_WRITER = """
import subprocess, sys
import subprocess
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
    with pytest.raises(RuntimeError, match=r"still alive 0\.3 s after SIGKILL"):
        session.wait_for_group(4242, exit_s=0.1, kill_s=0.3)
    assert killed
