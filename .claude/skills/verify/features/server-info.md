# Server info

The `server_info` tool tells a client which commit the server runs from, which Python it runs on and which tools it offers. It is the first call that proves a client is connected to the right checkout.

## Sub-features

- `info-scripted` returns the head SHA, the Python version and the tool list through `cad-call`.
- `info-claude` returns the same through a Claude Code session.
- `info-unknown-tool` returns an error result that names a tool that does not exist.
- `info-extra-argument` returns a validation error for an argument the tool does not declare.
- `info-bad-arguments` exits 2 for arguments that are not a JSON object.
- `info-app-step` passes inside `uv run verify`.

## How to get to it (user POV)

- Run `uv run cad-call server_info '{}'` in a terminal.
- Ask Claude Code, with the repo's `.mcp.json` loaded, to call the `server_info` tool.
- Run `uv run verify` and read the `app` line.

## Driving it with cad-call and claude_session.py

Preconditions:

- `uv sync --frozen` has run.
- The Doctor commands in `../SKILL.md` agree on the SHA.

- **Scripted call.** Run `uv run cad-call server_info '{}'`. Exit code `0`. `structuredContent` has `sha` equal to `git rev-parse HEAD`, `dirty` true when `git status --porcelain` is not empty, a `python` version and `tools` equal to `["build_variant", "confirm_requirements", "create_brief", "list_materials", "list_requirements", "propose_requirements", "score_variant", "server_info"]`.
- **Claude Code call.** Run `uv run python .claude/skills/verify/scripts/claude_session.py "call the server_info tool and print its sha" "$EVIDENCE/claude-server-info.json"`. Output starts with `init: cad connected`, has a `tool call: mcp__cad__server_info {}` line, and the reply contains the head SHA.
- **Unknown tool.** Run `uv run cad-call no_such_tool '{}'`. Exit code `1`. The result has `isError` true and text `Unknown tool: no_such_tool`.
- **Extra argument.** Run `uv run cad-call server_info '{"x": 1}'`. Exit code `1`. The result has `isError` true and text that says `Extra inputs are not permitted`.
- **App step.** Run `uv run verify --only app`. Prints `ok   app`, then `server_info sha <head sha> dirty=True` or `dirty=False`, and exits 0. It fails when git fails, when either SHA is `unknown`, or when the SHAs differ.
- **Malformed arguments.** Run `uv run cad-call server_info '{not json'`. Exit code `2` and a usage error on stderr, with no traceback.

## Gotchas

- `claude mcp list` shows `cad` as `Pending approval` until an interactive `claude` session in the repo approves the `.mcp.json` server. The headless drive passes `--mcp-config` and does not need it.
- `--output-format json` without `--verbose` prints only the final result, with no init event, so the connection check cannot run.
- A SHA from `server_info` that differs from `git rev-parse HEAD` means the server started from another checkout.
- `cad-call` prints server log lines on stderr. Read stdout for the JSON.
