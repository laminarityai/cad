import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

ROOT: Final = Path(__file__).resolve().parents[2]
SESSION: Final = ROOT / ".claude/skills/verify/scripts/claude_session.py"
HUMAN: Final = ROOT / ".claude/skills/verify/scripts/human.py"
ASK: Final = "mcp__cad__ask_to_confirm"
GUARD_LINES: Final = (
    "tools outside cad",
    "tools available outside cad",
    "cad is not connected",
    "claude exited",
)


@dataclass(frozen=True, slots=True)
class SessionFacts:
    model: str | None
    cost_usd: float | None
    turns: int | None
    ask_calls: int
    tool_calls: int
    is_error: bool


@dataclass(frozen=True, slots=True)
class SessionRun:
    exit_code: int | None
    timed_out: bool
    note: str
    facts: SessionFacts


def run_session(
    prompt: str, home: Path, transcript: Path, human_log: Path, model: str, timeout_s: float
) -> SessionRun:
    """The process runs in its own session so a timeout stops claude and the cad server with it."""
    command = [
        sys.executable,
        str(SESSION),
        "--model",
        model,
        "--opener",
        str(HUMAN),
        "--home",
        str(home),
        prompt,
        str(transcript),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=ROOT,
        env={**os.environ, "CAD_HUMAN_LOG": str(human_log)},
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout_s)
        timed_out = False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
        timed_out = True
    return SessionRun(
        None if timed_out else process.returncode,
        timed_out,
        failure_note(output),
        read_transcript(transcript),
    )


def failure_note(output: str) -> str:
    lines = output.strip().splitlines()
    said = [line for line in lines if line.startswith(GUARD_LINES)]
    return "; ".join(said) or (lines[-1] if lines else "no output")


def read_transcript(path: Path) -> SessionFacts:
    try:
        events = cast(list[dict[str, Any]], json.loads(path.read_text()))
    except (OSError, ValueError):
        return SessionFacts(None, None, None, 0, 0, True)
    model: str | None = None
    names: list[str] = []
    result: dict[str, Any] = {}
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            model = cast(str | None, event.get("model"))
        elif event.get("type") == "result":
            result = event
        elif event.get("type") == "assistant":
            content = cast(list[dict[str, Any]], event["message"]["content"])
            names += [cast(str, b["name"]) for b in content if b.get("type") == "tool_use"]
    return SessionFacts(
        model=model,
        cost_usd=cast(float | None, result.get("total_cost_usd")),
        turns=cast(int | None, result.get("num_turns")),
        ask_calls=names.count(ASK),
        tool_calls=len(names),
        is_error=bool(result.get("is_error", True)),
    )
