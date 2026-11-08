import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def test_a_session_that_can_reach_a_tool_outside_cad_fails(tmp_path: Path) -> None:
    done = drive("bash_reachable.json", tmp_path)
    assert done.returncode == 1
    assert "tools available outside cad: Bash" in done.stdout


def test_a_tool_from_another_mcp_server_is_outside_cad(tmp_path: Path) -> None:
    done = drive("other_mcp_server.json", tmp_path)
    assert done.returncode == 1
    assert "tools available outside cad: mcp__other__x" in done.stdout
    assert "tools outside cad: mcp__other__x" in done.stdout


def cad_entry(tmp_path: Path, *flags: str) -> dict[str, Any]:
    argv = tmp_path / "argv.json"
    stub = tmp_path / "bin" / "claude"
    stub.parent.mkdir(parents=True)
    stub.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"open({str(argv)!r}, 'w').write(json.dumps(sys.argv))\n"
        f"print(open({str(TRANSCRIPTS / 'cad_only.json')!r}).read())\n"
    )
    stub.chmod(0o755)
    done = subprocess.run(
        [sys.executable, str(SESSION), *flags, "a prompt", str(tmp_path / "o")],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{stub.parent}{os.pathsep}{os.environ['PATH']}"},
    )
    assert done.returncode == 0, done.stdout
    arguments = json.loads(argv.read_text())
    config = json.loads(arguments[arguments.index("--mcp-config") + 1])
    return config["mcpServers"]["cad"]


def test_the_opener_flag_reaches_the_cad_server_arguments(tmp_path: Path) -> None:
    assert cad_entry(tmp_path, "--opener", "/bin/echo")["args"][-2:] == ["--opener", "/bin/echo"]


def test_the_server_runs_in_a_fresh_home_unless_told_otherwise(tmp_path: Path) -> None:
    fresh = Path(cad_entry(tmp_path / "fresh")["env"]["HOME"])
    assert fresh.is_dir() and not any(fresh.iterdir()) and fresh != Path.home()
    kept = tmp_path / "kept"
    assert cad_entry(tmp_path / "kept-run", "--home", str(kept))["env"] == {"HOME": str(kept)}
    assert "env" not in cad_entry(tmp_path / "real", "--real-home")
