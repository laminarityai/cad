import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / ".claude/skills/verify/scripts/claude_session.py"
TRANSCRIPTS = Path(__file__).resolve().parent / "transcripts"


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


def test_a_session_that_calls_a_tool_outside_cad_fails(tmp_path: Path) -> None:
    done = drive("bash_reads_materials.json", tmp_path)
    assert done.returncode == 1
    assert "tools outside cad: Bash, Bash, ToolSearch" in done.stdout


def test_a_session_that_calls_only_cad_tools_passes(tmp_path: Path) -> None:
    done = drive("cad_only.json", tmp_path)
    assert done.returncode == 0, done.stdout
    assert "tool call: mcp__cad__score_variant" in done.stdout
