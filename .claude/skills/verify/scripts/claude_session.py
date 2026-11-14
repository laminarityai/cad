"""Usage: uv run python .claude/skills/verify/scripts/claude_session.py [--model <alias>]
    [--opener <program>] [--home <dir> | --real-home] "<prompt>" <transcript.json>

The cad server runs with HOME set to --home, else $CAD_HOME, else a fresh temporary directory, so a
drive never writes to the operator's ~/.cad (issue #81). --real-home opts out.

Claude Code skips a broken MCP server entry and still exits 0, so this script fails unless the
system/init event lists `cad` as connected with no mcp_server_errors. It also fails when the
init event lists a tool outside cad, or the transcript has a tool call outside cad that Claude Code
did not refuse. A call Claude Code refused as "No such tool available", such as a cad tool named
without its prefix, reached nothing: it is printed apart and does not fail the session.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
CAD_TOOL_PREFIX = "mcp__cad__"
FAILURE_LINES = (
    "claude exited",
    "cad is not connected",
    "tools available outside cad:",
    "tools outside cad:",
)


def failure_of(stdout: str, stderr: str) -> str:
    """Why a drive exited 1: the lines in FAILURE_LINES this script printed, else the last line of
    the traceback it raised. Its last stdout line is often the model's reply, so it is never the
    reason. The eval harnesses read a failed drive through this one function."""
    said = [line for line in stdout.splitlines() if line.startswith(FAILURE_LINES)]
    raised = stderr.strip().splitlines()
    return "; ".join(said) or (raised[-1] if raised else "the session reported an error")


def refusal(name: str) -> str:
    """The tool result Claude Code returns for a call to a tool it does not have."""
    return f"<tool_use_error>Error: No such tool available: {name}</tool_use_error>"


def mcp_config(opener: str | None = None, home: Path | None = None) -> str:
    config = json.loads((ROOT / ".mcp.json").read_text())
    cad = config["mcpServers"]["cad"]
    if home is not None:
        cad["env"] = {"HOME": str(home)}
    cad["args"] = [
        "--directory",
        str(ROOT),
        *cad["args"],
        *(["--opener", opener] if opener else []),
    ]
    return json.dumps(config)


def main(
    prompt: str,
    transcript: Path,
    model: str | None = None,
    opener: str | None = None,
    home: Path | None = None,
) -> int:
    print(f"server home: {home or Path.home()}")
    with tempfile.TemporaryDirectory(prefix="claude-session-") as empty:
        done = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--mcp-config",
                mcp_config(opener, home),
                "--strict-mcp-config",
                "--tools",
                "",
                "--allowedTools",
                f"{CAD_TOOL_PREFIX}*",
                "--setting-sources",
                "project",
                "--disable-slash-commands",
                "--output-format",
                "json",
                "--verbose",
                *(["--model", model] if model else []),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=empty,
        )
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(done.stdout)
    if done.returncode != 0:
        print(f"claude exited {done.returncode}\n{done.stderr}")
        return 1
    events: list[dict[str, Any]] = json.loads(done.stdout)
    init = next(e for e in events if e.get("type") == "system" and e.get("subtype") == "init")
    servers = {s["name"]: s["status"] for s in init.get("mcp_servers", [])}
    if servers.get("cad") != "connected" or init.get("mcp_server_errors"):
        print(f"cad is not connected: {servers} errors={init.get('mcp_server_errors')}")
        return 1
    print("init: cad connected")
    reachable = [t for t in init["tools"] if not t.startswith(CAD_TOOL_PREFIX)]
    if reachable:
        print(f"tools available outside cad: {', '.join(reachable)}")
    errors = {
        block["tool_use_id"]: block["content"]
        for event in events
        if event.get("type") == "user" and isinstance(event["message"]["content"], list)
        for block in event["message"]["content"]
        if block.get("type") == "tool_result" and block.get("is_error") is True
    }
    foreign: list[str] = []
    refused: list[str] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in event["message"]["content"]:
            if block.get("type") != "tool_use":
                continue
            if block["name"].startswith(CAD_TOOL_PREFIX):
                print(f"tool call: {block['name']} {json.dumps(block['input'])}")
            elif errors.get(block["id"]) == refusal(block["name"]):
                refused.append(block["name"])
            else:
                foreign.append(block["name"])
    result = next(e for e in events if e.get("type") == "result")
    print(f"result: {result['result']}")
    if refused:
        print(f"tool calls Claude Code refused: {', '.join(refused)}")
    if foreign:
        print(f"tools outside cad: {', '.join(foreign)}")
    return 1 if reachable or foreign or result.get("is_error") else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument(
        "--opener", help="program the cad server runs with each sign-in link to the page"
    )
    homes = parser.add_mutually_exclusive_group()
    homes.add_argument(
        "--home", type=Path, help="HOME for the server, kept across sessions (default $CAD_HOME)"
    )
    homes.add_argument("--real-home", action="store_true", help="run the server in your own HOME")
    parser.add_argument("prompt")
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    home = None
    shared = args.home or os.environ.get("CAD_HOME")
    if shared and not args.real_home:
        home = Path(shared).resolve()
        home.mkdir(parents=True, exist_ok=True)
    elif not args.real_home:
        home = Path(tempfile.mkdtemp(prefix="cad-home-"))
    sys.exit(main(args.prompt, args.transcript, args.model, args.opener, home))
