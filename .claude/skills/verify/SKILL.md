---
name: verify
description: Drive the cad MCP server the way a client does, either with one scripted stdio call (`cad-call`) or with a headless Claude Code session (`claude -p` through `.mcp.json`). Use it to prove any change to a tool, the server, or what an MCP client sees.
---

# Verify the cad MCP server

The product is a local MCP server over stdio (`uv run cad-server`). It has no screen. Evidence is a saved JSON transcript or a terminal capture. Run every command from the repo root, in a checkout where `uv sync --frozen` has run.

## Launch

There is no long-running process to start. Each drive starts its own server and stops it when the call ends.

```
uv sync --frozen
```

Ready means `uv run cad-call server_info '{}'` exits 0 (see Doctor).

## Doctor

Run first whenever anything looks off. All three are read-only.

```
uv run cad-call server_info '{}'
git rev-parse HEAD
claude --version
```

Pass when `structuredContent.sha` in the first output equals the second output. A different SHA means you are driving another checkout. `claude mcp list` shows `cad` as `Pending approval` until the repo's `.mcp.json` server is approved once in an interactive `claude` session. The headless `claude -p` drive below does not need that approval.

## Drive

Scripted call, one tool per run. Output is the MCP result as JSON, exit code 1 when the result is an error.

```
uv run cad-call <tool> '<json args>'
```

Tools today: `server_info` (no arguments). A tool rejects any argument it does not declare. An unknown tool name returns an error result naming the tool.

Claude Code session. This runs `claude -p` with `--mcp-config .mcp.json --strict-mcp-config --allowedTools 'mcp__cad__*' --output-format json --verbose`, saves the event transcript, and fails unless the `system/init` event lists `cad` as `connected` with no `mcp_server_errors`. Claude Code skips a broken `.mcp.json` entry and still exits 0, so never run `claude -p` against the server without that check. `--verbose` is what puts the init event in the JSON output.

```
uv run python .claude/skills/verify/scripts/claude_session.py "call the server_info tool and print its sha" /tmp/swarm-<pr-id>/worker-<n>/claude-server-info.json
```

It prints `init: cad connected`, one `tool call: mcp__cad__<name> <args>` line per MCP call, and the final reply.

The whole gate, which includes an app step that calls `server_info` and compares the SHA to `git rev-parse HEAD`:

```
uv run verify
```

## Evidence

- Save `cad-call` output with `> /tmp/swarm-<pr-id>/worker-<n>/<slug>.json` and the exit code next to it.
- Save the Claude Code transcript at the path you pass to `claude_session.py`.
- Prove the real path. A claim about what a client sees needs a `claude_session.py` run, not only a unit test or `cad-call`.
- Capture the call and the result. The transcript has both. For a tool that writes files, also list the files.
- The server logs to stderr only. Stdout carries the protocol, so a stray `print` in a tool breaks every client.

## Cleanup

Nothing to tear down. `cad-call` and `claude_session.py` each end their own server process. After a run that was killed, check for leftovers by exact command, and stop only the PIDs this run started.

```
pgrep -fl "cad.server"
```

Never use `pkill` by name. Keep the files under `/tmp/swarm-<pr-id>/`, because they are the evidence.

## Helpers

- `scripts/claude_session.py "<prompt>" <transcript.json>` is shown in Drive. It exits 1 when `cad` is not connected, when `claude` fails, or when the session reports an error.

Feature recipes live in [features/README.md](features/README.md).
