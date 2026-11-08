"""Usage: uv run python .claude/skills/verify/scripts/claude_session.py [--model <alias>]
    [--opener <program>] "<prompt>" <transcript.json>

Claude Code skips a broken MCP server entry and still exits 0, so this script fails unless the
system/init event lists `cad` as connected with no mcp_server_errors. It also fails when the
init event lists a tool outside cad, or the transcript has a tool call outside cad.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
CAD_TOOL_PREFIX = "mcp__cad__"


def mcp_config(opener: str | None = None) -> str:
    config = json.loads((ROOT / ".mcp.json").read_text())
    cad = config["mcpServers"]["cad"]
    cad["args"] = [
        "--directory",
        str(ROOT),
        *cad["args"],
        *(["--opener", opener] if opener else []),
    ]
    return json.dumps(config)


def main(prompt: str, transcript: Path, model: str | None = None, opener: str | None = None) -> int:
    with tempfile.TemporaryDirectory(prefix="claude-session-") as empty:
        done = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--mcp-config",
                mcp_config(opener),
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
    foreign: list[str] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in event["message"]["content"]:
            if block.get("type") != "tool_use":
                continue
            if block["name"].startswith(CAD_TOOL_PREFIX):
                print(f"tool call: {block['name']} {json.dumps(block['input'])}")
            else:
                foreign.append(block["name"])
    result = next(e for e in events if e.get("type") == "result")
    print(f"result: {result['result']}")
    if foreign:
        print(f"tools outside cad: {', '.join(foreign)}")
    return 1 if reachable or foreign or result.get("is_error") else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument("--opener", help="program the cad server runs with the page URL")
    parser.add_argument("prompt")
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    sys.exit(main(args.prompt, args.transcript, args.model, args.opener))
