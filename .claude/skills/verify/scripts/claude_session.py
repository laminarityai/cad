"""Usage: uv run python .claude/skills/verify/scripts/claude_session.py "<prompt>" <transcript.json>

Claude Code skips a broken .mcp.json entry and still exits 0, so this script fails unless the
system/init event lists `cad` as connected with no mcp_server_errors.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]


def main(prompt: str, transcript: Path) -> int:
    done = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--mcp-config",
            ".mcp.json",
            "--strict-mcp-config",
            "--allowedTools",
            "mcp__cad__*",
            "--output-format",
            "json",
            "--verbose",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
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
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in event["message"]["content"]:
            if block.get("type") == "tool_use" and block["name"].startswith("mcp__cad__"):
                print(f"tool call: {block['name']} {json.dumps(block['input'])}")
    result = next(e for e in events if e.get("type") == "result")
    print(f"result: {result['result']}")
    return 1 if result.get("is_error") else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], Path(sys.argv[2])))
