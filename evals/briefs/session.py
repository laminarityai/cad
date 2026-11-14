import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol, cast

from asking import Call

ROOT: Final = Path(__file__).resolve().parents[2]
SESSION: Final = ROOT / ".claude/skills/verify/scripts/claude_session.py"
HUMAN: Final = ROOT / ".claude/skills/verify/scripts/human.py"
CAD: Final = "mcp__cad__"
ASK: Final = f"{CAD}ask_to_confirm"
EXIT_WAIT_S: Final = 30.0


@dataclass(frozen=True, slots=True)
class SessionFacts:
    """`refused_calls` counts the calls to a tool outside cad. `claude_session.py` fails a session
    on any such call that Claude Code did not refuse, so in a session that passed each one was
    refused and reached nothing."""

    model: str | None
    cost_usd: float | None
    turns: int | None
    ask_calls: int
    tool_calls: int
    is_error: bool
    refused_calls: int = 0
    calls: tuple[Call, ...] = ()


@dataclass(frozen=True, slots=True)
class SessionRun:
    exit_code: int | None
    timed_out: bool
    note: str
    facts: SessionFacts


def run_session(
    prompt: str, home: Path, transcript: Path, human_log: Path, model: str, timeout_s: float
) -> SessionRun:
    """The process runs in its own session so a timeout stops claude and the cad server with it.
    Either way it returns only once every process of that session has exited."""
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
        stderr=subprocess.PIPE,
        text=True,
        cwd=ROOT,
        env={**os.environ, "CAD_HUMAN_LOG": str(human_log)},
        start_new_session=True,
    )
    try:
        output, raised = process.communicate(timeout=timeout_s)
        timed_out = False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, raised = process.communicate()
        timed_out = True
    _wait_for_group(process.pid)
    return SessionRun(
        None if timed_out else process.returncode,
        timed_out,
        failure_note(output, raised),
        read_transcript(transcript),
    )


def _wait_for_group(group: int) -> None:
    """The cad server can still store a check record after claude exits. Wait for it to exit,
    then stop what is left, so no record lands after the harness reads the stores."""
    deadline = time.monotonic() + EXIT_WAIT_S
    while _alive(group):
        if time.monotonic() > deadline:
            with suppress(ProcessLookupError):
                os.killpg(group, signal.SIGKILL)
        time.sleep(0.1)


def _alive(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    return True


def failure_note(output: str, raised: str) -> str:
    """Why the session failed, read by the driver's own rule."""
    return _driver().failure_of(output, raised)


class Driver(Protocol):
    def failure_of(self, stdout: str, stderr: str) -> str: ...


def _driver() -> Driver:
    """The session driver, loaded once by path and shared, as it is a script and not a package."""
    if "claude_session" not in sys.modules:
        spec = importlib.util.spec_from_file_location("claude_session", SESSION)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules["claude_session"] = module
    return cast(Driver, cast(object, sys.modules["claude_session"]))


def read_transcript(path: Path) -> SessionFacts:
    try:
        events = cast(list[dict[str, Any]], json.loads(path.read_text()))
    except (OSError, ValueError):
        return SessionFacts(None, None, None, 0, 0, True)
    model: str | None = None
    calls: list[Call] = []
    result: dict[str, Any] = {}
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            model = cast(str | None, event.get("model"))
        elif event.get("type") == "result":
            result = event
        elif event.get("type") == "assistant":
            content = cast(list[dict[str, Any]], event["message"]["content"])
            calls += [
                (cast(str, b["name"]), cast(dict[str, Any], b.get("input") or {}))
                for b in content
                if b.get("type") == "tool_use"
            ]
    names = [name for name, _ in calls]
    return SessionFacts(
        model=model,
        cost_usd=cast(float | None, result.get("total_cost_usd")),
        turns=cast(int | None, result.get("num_turns")),
        ask_calls=names.count(ASK),
        tool_calls=len(names),
        is_error=bool(result.get("is_error", True)),
        refused_calls=sum(not name.startswith(CAD) for name in names),
        calls=tuple(calls),
    )
