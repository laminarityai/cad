"""The harness reads a session's stores only after every process the session started has exited,
so a check record the cad server writes after Claude Code exits is read, not missed."""

from pathlib import Path

import pytest
import session
from session import run_session

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
