---
name: verify
description: Drive the cad MCP server the way a client does, either with one scripted stdio call (`cad-call`) or with a headless Claude Code session (`claude -p` through `.mcp.json`). Use it to prove any change to a tool, the server, or what an MCP client sees.
---

# Verify the cad MCP server

The product is a local MCP server over stdio (`uv run cad-server`). It has no screen. Evidence is a saved JSON transcript or a terminal capture. Run every command from the repo root, in a checkout where `uv sync --frozen` has run. Run each command as written, and replace only a `<placeholder>` in angle brackets or the `$EVIDENCE` variable.

Launch every Claude Code session from the repo root. `.mcp.json` starts the server with `uv run --frozen cad-server`, and `uv` finds the project from the launcher's working directory. `${CLAUDE_PROJECT_DIR}` does not help. With `claude -p --mcp-config <absolute path>` run from `/tmp`, the variable was unset, and an entry that used it as `uv run --frozen --project "${CLAUDE_PROJECT_DIR}" cad-server` failed to connect.

Set the evidence directory once per run. A swarm lane sets it to its own lane directory.

```
export EVIDENCE=$(mktemp -d)
```

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

Pass when `structuredContent.sha` in the first output equals the second output. A different SHA means you are driving another checkout. `structuredContent.dirty` is true when `git status --porcelain` is not empty, so a true value means the SHA does not describe the code that ran. `claude mcp list` shows `cad` as `Pending approval` until the repo's `.mcp.json` server is approved once in an interactive `claude` session. The headless `claude -p` drive below does not need that approval.

## Drive

Scripted call, one tool per run. Output is the MCP result as JSON, exit code 1 when the result is an error.

```
uv run cad-call <tool> '<json args>'
```

Tools today: `server_info` (no arguments). A tool rejects any argument it does not declare. An unknown tool name returns an error result naming the tool. Arguments that are not a JSON object exit 2 with a usage error, and a tool error exits 1.

Claude Code session. This runs `claude -p` with `--mcp-config .mcp.json --strict-mcp-config --allowedTools 'mcp__cad__*' --output-format json --verbose`, saves the event transcript, and fails unless the `system/init` event lists `cad` as `connected` with no `mcp_server_errors`. Claude Code skips a broken `.mcp.json` entry and still exits 0, so never run `claude -p` against the server without that check. `--verbose` is what puts the init event in the JSON output.

```
uv run python .claude/skills/verify/scripts/claude_session.py "call the server_info tool and print its sha" "$EVIDENCE/claude-server-info.json"
```

It prints `init: cad connected`, one `tool call: mcp__cad__<name> <args>` line per MCP call, and the final reply.

The whole gate. Its app step calls `server_info`, runs `git rev-parse HEAD` itself, and fails when git fails, when either SHA is `unknown`, or when they differ. It prints the SHA and `dirty=<true or false>`, and a dirty tree does not fail it:

```
uv run verify
```

## Evidence

- Save `cad-call` output with `> "$EVIDENCE/<slug>.json"` and the exit code next to it.
- Save the Claude Code transcript at the path you pass to `claude_session.py`.
- Prove the real path. A claim about what a client sees needs a `claude_session.py` run, not only a unit test or `cad-call`.
- Capture the call and the result. The transcript has both. For a tool that writes files, also list the files.
- The server logs to stderr. Stdout carries the protocol. With mcp 2.3.0 the SDK points fd 1 at stderr while it serves, so a stray `print` in a tool does not corrupt the stream. Output still unflushed at shutdown can reach the real stdout, and the client then logs a parse warning. Log through `logging` anyway.

## Cleanup

Nothing to tear down. `cad-call` and `claude_session.py` each end their own server process. After a run that was killed, look for leftovers with a filter on this checkout's interpreter. `pgrep -f` takes a regular expression and matches the whole command line, so a bare `cad.server` also matches other checkouts' servers and `uv run cad-server`. Stop only the PIDs this run started.

```
pgrep -fl "$PWD/.venv/bin/python.*(-m cad\.server|bin/cad-server)"
```

Never use `pkill` by name. Keep the files under `$EVIDENCE`, because they are the evidence.

## Helpers

- `scripts/claude_session.py "<prompt>" <transcript.json>` is shown in Drive. It exits 1 when `cad` is not connected, when `claude` fails, or when the session reports an error.

Feature recipes live in [features/README.md](features/README.md).
