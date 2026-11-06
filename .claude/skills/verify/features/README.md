# cad verification map

This directory is the maintained source for verifying what an MCP client sees from the cad server. Read this index, then use the matching feature file as the recipe.

## Baseline preconditions

- Work in a checkout where `uv sync --frozen` has run.
- Run `uv run cad-call server_info '{}'` and require its `sha` to equal `git rev-parse HEAD`.
- Every Claude Code session goes through `scripts/claude_session.py`, never a bare `claude -p`.

## Driving conventions

- Run each command as written. Keep quoted names and flags unchanged, and replace only a `<placeholder>` in angle brackets or the `$EVIDENCE` variable, which `../SKILL.md` sets.
- Save evidence under `$EVIDENCE`.
- Launch Claude Code sessions from the repo root.
- Report an unreachable path with the attempted command and the unmet precondition. Do not report a skipped entry point as verified through a different path.

## Proof and skip reporting

- A scripted proof includes the command, the JSON result and the exit code.
- A Claude Code proof includes the transcript, with `cad` connected in the init event and the `mcp__cad__*` tool call in the events.

## Features

- [Server info](./server-info.md) covers the `server_info` tool through a scripted call and through Claude Code, plus the error results for bad calls.
- [Build variant](./build-variant.md) covers the `build_variant` tool: each outcome kind, the stored variant, Docker down, and the `sandbox image` verify step.
- [Run checks](./run-checks.md) covers `cad-sandbox run-checks`: the three geometric checks on a built variant, the material key, the derived `result.step`, and the refusal of stale variants.
