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

There is no long-running process to start. Each drive starts its own server and stops it when the call ends. `build_variant` runs each build in a Docker container, and `cad-sandbox run-checks` runs the checks in a second one, so Docker Desktop must run, and the sandbox image must exist.

```
uv sync --frozen
uv run cad-sandbox build-image
```

The second command prints `sandbox image cad-sandbox:<tag> is current` when the image exists, and builds it otherwise, which takes minutes the first time. With Docker down it prints one line that names the cause and exits 1.

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

Tools today: `server_info` (no arguments), `build_variant` (`code`, the build123d Python source), `score_variant` (`variant_id`, `material_key`) and `list_materials` (no arguments). A tool rejects any argument it does not declare. An unknown tool name returns an error result naming the tool. Arguments that are not a JSON object exit 2 with a usage error, and a tool error exits 1.

Claude Code session. This runs `claude -p` with `--mcp-config .mcp.json --strict-mcp-config --allowedTools 'mcp__cad__*' --output-format json --verbose`, saves the event transcript, and fails unless the `system/init` event lists `cad` as `connected` with no `mcp_server_errors`. Claude Code skips a broken `.mcp.json` entry and still exits 0, so never run `claude -p` against the server without that check. `--verbose` is what puts the init event in the JSON output.

```
uv run python .claude/skills/verify/scripts/claude_session.py "call the server_info tool and print its sha" "$EVIDENCE/claude-server-info.json"
```

It prints `init: cad connected`, one `tool call: mcp__cad__<name> <args>` line per MCP call, and the final reply.

Build a variant from a file. `jq -Rs '{code: .}'` turns the file into the JSON object `cad-call` takes:

```
uv run cad-call build_variant "$(jq -Rs '{code: .}' < tests/sandbox/parts/plate.py)" > "$EVIDENCE/build-plate.json"
```

Variants live in `~/.cad/variants/<variant_id>/`. The same code returns its stored outcome without a new build. A build stores `result.brep` only.

Score a built variant. `score_variant` runs the three checks and prints the scorecard as the MCP result, and it stores the same scorecard in `~/.cad/variants/<variant_id>/scorecard.json`. `list_materials` lists the keys it accepts:

```
uv run cad-call list_materials '{}' > "$EVIDENCE/list-materials.json"
uv run cad-call score_variant "{\"variant_id\": \"$(jq -r .structuredContent.variant_id "$EVIDENCE/build-plate.json")\", \"material_key\": \"prusament-pla\"}" > "$EVIDENCE/score-plate.json"
```

The checks alone, without a scorecard, run through the sandbox CLI. It prints the `CheckRun` as JSON, exits 0 when the run completed even if a check failed, and exits 1 with one line for a refusal or an unavailable sandbox:

```
uv run cad-sandbox run-checks "$(jq -r .structuredContent.variant_id "$EVIDENCE/build-plate.json")" prusament-pla > "$EVIDENCE/checks-plate.json"
```

The first run of the checks on a variant (either command) also writes `~/.cad/variants/<variant_id>/result.step`, derived from the BREP the checks measured. Any edit under `src/cad/sandbox/` or `src/cad/variants/` changes every variant id, so ids from before the edit are refused with `StaleVariant`: build the code again.

The whole gate. Its app step calls `server_info`, runs `git rev-parse HEAD` itself, and fails when git fails, when either SHA is `unknown`, or when they differ. It prints the SHA and `dirty=True` or `dirty=False`, and a dirty tree does not fail it:

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

Nothing to tear down. `cad-call` and `claude_session.py` each end their own server process, and each build removes its own container. A killed server cannot remove its container, so each server start removes every exited sandbox container whose `cad.owner-pid` process is gone. It never removes a running container. To see what is left, list the sandbox containers. The `cad.sandbox` label is `build` for a build and `check` for a check run:

```
docker ps -a --filter label=cad.sandbox
```

Look for leftover servers with a filter on this checkout's interpreter. `pgrep -f` takes a regular expression and matches the whole command line, so a bare `cad.server` also matches other checkouts' servers and `uv run cad-server`. Stop only the PIDs this run started.

```
pgrep -fl "$PWD/.venv/bin/python.*(-m cad\.server|bin/cad-server)"
```

Never use `pkill` by name. Keep the files under `$EVIDENCE`, because they are the evidence.

## Helpers

- `scripts/claude_session.py [--model <alias>] [--lean] "<prompt>" <transcript.json>` is shown in Drive. It exits 1 when `cad` is not connected, when `claude` fails, or when the session reports an error. `--lean` loads the repo's settings only, no skills and no built-in tools, so the model can call only the cad tools.

Feature recipes live in [features/README.md](features/README.md).
