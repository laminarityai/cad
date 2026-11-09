# cad verification map

This directory is the maintained source for verifying what a user of cad sees: the MCP tools through a client, and the confirmation page in a browser. Read this index, then use the matching feature file as the recipe.

## Baseline preconditions

- `uv sync --frozen` has run, and the Run setup of `../SKILL.md` set `EVIDENCE`, `CAD_HOME` and `CAD_BROWSER`.
- `HOME="$CAD_HOME" uv run cad-call server_info '{}'` reports the `sha` that `git rev-parse HEAD` prints.
- Every Claude Code session goes through `scripts/claude_session.py`, never a bare `claude -p`.
- Every confirmation page is answered by `scripts/browser.py`, except the cases `../SKILL.md` Helpers gives to `human.py`.

## Driving conventions

- Run each command as written. Replace only a `<placeholder>` or a variable `../SKILL.md` sets.
- One `CAD_HOME` and one browser per run. Build a part once and reuse its `variant_id`. The same code in the same home is a store hit.
- Report an unreachable path with the attempted command and the unmet precondition. Do not report a skipped entry point as verified through a different path.

## Proof and skip reporting

- A scripted proof includes the command, the JSON result and the exit code.
- A Claude Code proof includes the transcript, with `cad` connected in the init event and the `mcp__cad__*` tool calls in the events.
- A page proof includes `browser.jsonl`, the ARIA snapshot and the before and after screenshots.

## Features

Cost: **free** is `cad-call` alone (about 8 s of server start per call). **docker** starts a container for new code or a new check run. **browser** needs `browser.py start` once per run. **live** is a model session, which costs money and minutes. Each row's cheapest proof is the first one to run. Run the costlier rows only when the claim is about them.

| Feature | Covers | Cheapest proof | Costlier proofs |
|---|---|---|---|
| [Server info](./server-info.md) | `server_info`, bad calls, the `app` verify step | free | live: the Claude Code call |
| [Briefs](./briefs.md) | `create_brief`, `propose_requirements`, `ask_to_confirm`, `list_requirements`, the confirmation page, refusals | free: refusals, projects. browser: confirm, edit, decline, one page | live: the agent's flow, the adversary |
| [Build variant](./build-variant.md) | `build_variant` outcomes, the store, Docker down, variant sets | docker | live: the Claude Code call |
| [Run checks](./run-checks.md) | `cad-sandbox run-checks`: the four geometric checks, `result.step`, stale variants | docker | none |
| [Score variant](./score-variant.md) | `score_variant`, `scorecard` read-back, `list_materials`, `basis`, `made_of`, the allowlist | docker, plus browser for a confirmed brief | live: build and score, override |
| [Knowledge](./knowledge.md) | `search_knowledge` ranking | free | live: choosing between a hit and its near miss |
| [Research](./research.md) | `submit_research` and the research requests on a scorecard | docker + browser + network | none |
| [Test mode](./test-mode.md) | the Test mode guidance: score only the picked variant, report what no check measured as not checked | live (three sessions) | none |
| [Agree](./agree.md) | `evals/bakeoff/agree.py`: scorecards against the bake-off grader | docker: replay (60 builds, about 4 min) | live: 10 sessions, about 0.4 USD |
| [Brief set](./brief-set.md) | `evals/briefs/run.py`: the private brief set, traced numbers, friction | live (one session per brief) | none |
| [Context parts](./context-parts.md) | `propose_context_part`, the context part item on the confirmation page, and the `fit` check against each confirmed part | free: idempotent, declined, refusals (`tests/context_parts/`). docker: propose a built variant. docker + browser: confirm a part, score fit and clearance | live: the agent proposes a part and the person confirms it |
| [Hosted MCP and accounts](./hosted-mcp.md) | `cad-http`: `/mcp` over HTTP, the metadata, token kinds per route, tenancy, the lease, the usage cap | free: curl and `cad-call --url` with `cad-token` tokens | operator: `claude mcp login cad` against a Clerk instance |
| [Geometry](./geometry.md) | the person-only `geometry` operation: the mesh of a variant from the analysis image, for three-cad-viewer | free: pending, stored, retried (`tests/geometry/test_lane.py`). docker: the mesh volume against the `mass` check, and a screenshot in three-cad-viewer (`scripts/geometry.py`) | none: no agent reaches it |

## Phase 4 web app: NOT YET BUILT

`docs/design/phase-4.md` designs these surfaces. Unit 3 landed as [Hosted MCP and accounts](./hosted-mcp.md) and unit 5 as [Geometry](./geometry.md), and the rest do not exist yet. Each file names the check that §4 Sequencing gives the unit, the proof to write into the map when the unit lands, and the parts of the design it comes from. It names no selector, because the UI does not exist. When a unit lands, replace its file with a real recipe that follows the four-section shape of the files above.

- [Hosted confirmation](./phase-4/hosted-confirmation.md): the FastAPI page in the signed-in app, opened by URL elicitation. Unit 4.
- [Web shell](./phase-4/web-shell.md): the viewer and scorecards over SSE. Unit 6. Unit 5, geometry, is built: see [Geometry](./geometry.md).
- [Auto mode](./phase-4/auto-mode.md): the server-held Auto run and its stops. Units 7 and 9.
- [Chat](./phase-4/chat.md): the chat runtime and mode switcher. Unit 8.

Units 1 and 2 change tools that exist. Unit 1 adds `slot` to `build_variant`: update [Build variant](./build-variant.md) with its check (two builds into slot 2, the first in its history). Unit 2 moved the tools into a registry and deleted `scorecard.json`: [Score variant](./score-variant.md) reads a card back through `scorecard`.
