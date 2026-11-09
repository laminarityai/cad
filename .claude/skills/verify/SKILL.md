---
name: verify
description: Drive the cad MCP server the way a client does (one scripted stdio call with `cad-call`, or a headless Claude Code session with `claude_session.py`) and drive its confirmation page in a real Chromium (`browser.py`). Use it to prove any change to a tool, the server, the confirmation page, or what an MCP client sees.
---

# Verify cad

What a user touches today:

- **The MCP server over stdio** (`uv run cad-server`). Drive it with `cad-call` (one tool call) or `claude_session.py` (a real Claude Code session).
- **The confirmation page** that `ask_to_confirm` opens on 127.0.0.1. Drive it in a real browser with `browser.py`.

- **The MCP server over HTTP** (`uv run cad-http`), with accounts. Drive it with `curl` and `cad-call --url`: [features/hosted-mcp.md](features/hosted-mcp.md).

The rest of the phase 4 web app (chat, viewer, live scorecards, Auto mode) is designed in `docs/design/phase-4.md` and not built. [features/phase-4/](features/phase-4/) names the proof to write when each unit lands.

Run every command from the repo root. Run each command as written, and replace only a `<placeholder>` or a `$VARIABLE` this file sets.

## Run setup

Set these once per run. A swarm lane sets its own.

```
export EVIDENCE=$(mktemp -d)
export CAD_HOME="$EVIDENCE/home"
export CAD_BROWSER="$EVIDENCE/browser"
```

`CAD_HOME` is the server's `HOME` for the whole run, so a variant built once is a store hit for every later call, and briefs confirmed in one step are visible in the next. `claude_session.py` uses `$CAD_HOME` when it is set. Put `HOME="$CAD_HOME"` in front of every `cad-call` and every `cad-sandbox run-checks`. Never drive the server in your own `HOME`: it writes to the operator's `~/.cad` (issue #81).

## Cost: take the cheapest path that proves the claim

| Path | Cost per use | Use it to prove |
|---|---|---|
| `cad-call` on a tool that starts no container | about 8 s (server start), no Docker, no model | a tool's result, a refusal, stored files |
| `cad-call build_variant`, `score_variant`, `cad-sandbox run-checks` | one container, about 20 s for new code. The same code in the same `CAD_HOME` is a store hit and starts none | a build, a check, a scorecard |
| `browser.py` | one Chromium per run: about 13 s on the first launch after install, 2 s after that. Each page adds about 2 s | what the person sees and does on the confirmation page |
| `claude_session.py` | a live model session: money and 30 s to several minutes | what the agent does: which tools it calls, what it says |

Confirming a brief needs no model: create the brief, propose and call `ask_to_confirm` with `cad-call`, with the browser as the person (see Drive). Use a live session only when the claim is about the agent's behaviour. Each feature file in [features/README.md](features/README.md) lists its cheapest proof.

## Launch

```
uv sync --frozen
uv run playwright install chromium
uv run cad-sandbox build-image
uv run python .claude/skills/verify/scripts/browser.py start "$CAD_BROWSER"
```

- `playwright install chromium` is needed once per machine. It deletes browsers of other Playwright versions that it thinks are unused.
- `build-image` is needed only for recipes that start a container. It prints `sandbox image cad-sandbox:<tag> is current` and then the same line for `cad-analysis:<tag>`, or builds a missing image, which takes minutes. With Docker down it prints the cause and exits 1.
- `browser.py start` is needed only for recipes that open the confirmation page. It returns when the browser answers, and prints `browser ready: {...}` and `opener: <path>`. Running it again on the same directory reuses the running browser.

There is no long-running server. Each `cad-call` and each Claude Code session starts its own server and stops it.

## Doctor

Run these first whenever anything looks off. All of them are read-only.

```
HOME="$CAD_HOME" uv run cad-call server_info '{}'
git rev-parse HEAD
uv run python .claude/skills/verify/scripts/browser.py status "$CAD_BROWSER"
docker ps -a --filter label=cad.sandbox
claude --version
```

- `structuredContent.sha` must equal `git rev-parse HEAD`. A different SHA means another checkout. `dirty` true means the SHA does not describe the code that ran.
- `browser.py status` prints the daemon's pid, Chromium version, pages served and the current answer settings, or `no browser running for <dir>` with exit 1.
- `docker ps` lists sandbox containers (`cad.sandbox` is `build` or `check`). An exited one is left from a killed server. The next server start removes it.
- `claude --version` matters only for a live session.

## Drive

### cad-call

```
HOME="$CAD_HOME" uv run cad-call <tool> '<json args>'
```

It prints the MCP result as JSON and exits 1 when the result is an error and 2 when the arguments are not a JSON object. Tools: `server_info`, `build_variant`, `score_variant`, `scorecard`, `list_materials`, `create_brief`, `propose_requirements`, `propose_context_part`, `ask_to_confirm`, `list_requirements`, `search_knowledge`, `submit_research`. `jq -Rs '{code: .}' < <file>.py` turns a build123d file into the arguments `build_variant` takes. The stdio client passes the server only `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM` and `USER`.

### The confirmation page in a real browser

`browser.py start` writes `$CAD_BROWSER/bin/open`, the opener. The server runs it with the page URL, and it hands the URL to the one running Chromium. For each page n, the browser reads every section by its heading, saves `page-<n>.aria.yml` (the ARIA snapshot), types an edit if one is set, saves `page-<n>-before.png`, presses `Confirm` or `Decline all`, and saves `page-<n>-after.png` (the reply page). It appends JSON lines to `$CAD_BROWSER/browser.jsonl`:

- `{"page": n, "step": "page", "status": 200, "heading": ..., "sections": [{"heading", "brief", "quotes", "quotes_in_brief"}], "quotes_in_brief": true}`
- `{"page": n, "step": "edit", "shown": "150 g", "typed": "120 g", "fields": 1}`, only when an edit is set
- `{"page": n, "step": "confirm" | "decline", "status": 200, "said": "Recorded. You confirmed 1 and declined 0 on this page. ..."}`
- `{"page": n, "spent_token": "<token>"}`
- `{"page": n, "error": "..."}` for any failure, because the server discards the opener's output

Set how the person answers. The settings hold for every later page:

```
uv run python .claude/skills/verify/scripts/browser.py set "$CAD_BROWSER" answer=decline
uv run python .claude/skills/verify/scripts/browser.py set "$CAD_BROWSER" answer=confirm "edit=150 g=120 g"
uv run python .claude/skills/verify/scripts/browser.py set "$CAD_BROWSER" edit= delay=1
```

`edit=<shown>=<typed>` types `<typed>` into each `Change to` field whose placeholder is `<shown>`. `delay` is the seconds before answering (default 1). A declined page gets the note `scripted person declined`.

**Confirm with no model.** `cad-call` starts a server whose opener is `open` from `PATH`, so put the browser's `bin` first:

```
PATH="$CAD_BROWSER/bin:$PATH" HOME="$CAD_HOME" uv run cad-call ask_to_confirm '{"project_id": "<project_id>"}'
```

Never run `ask_to_confirm` through `cad-call` without that `PATH`: it runs the system `open` and shows a page on the operator's screen.

### Claude Code session

```
uv run python .claude/skills/verify/scripts/claude_session.py [--opener "$CAD_BROWSER/bin/open"] [--model <alias>] "<prompt>" "$EVIDENCE/<slug>.json"
```

It runs `claude -p` from an empty temporary directory, with only the cad tools (`--tools "" --allowedTools 'mcp__cad__*' --strict-mcp-config`), and saves the event transcript. It prints `server home: <path>`, `init: cad connected`, one `tool call: mcp__cad__<name> <args>` line per call, and `result: <reply>`. It exits 1 when `cad` is not connected, when the session can reach or calls a tool outside cad (`tools available outside cad:` or `tools outside cad:`), or when the session reports an error. Claude Code skips a broken MCP entry and still exits 0, so never run a bare `claude -p` against the server.

The session's server inherits the environment, so `CAD_HUMAN_ANSWER`, `CAD_HUMAN_EDIT` and `CAD_HUMAN_DELAY` in front of the command override the browser's settings for that session's pages.

### The gate

```
uv run verify
```

It runs the type checks, lint, format, file size, materials table, sandbox image, tests, and the `app` step, which fails unless `server_info` reports `git rev-parse HEAD`. A dirty tree prints `dirty=True` and does not fail.

## Evidence

Everything goes under `$EVIDENCE`: `cad-call` output as `<slug>.json`, transcripts, `$CAD_BROWSER/` (log, ARIA snapshots, screenshots) and `$CAD_HOME/.cad/` (the stores the run wrote).

- Prove the user's path. A claim about what the agent does needs a transcript. A claim about the page needs the browser's screenshots and log, not an HTTP probe.
- Capture the action and the result, then read the side effect from a second view: `list_requirements` after a page answer, the variant directory after a build, `scorecard` after a score.
- The spent token must not appear in any transcript: `grep -c "<spent_token>" <transcript>` prints `0`.

## Cleanup

```
uv run python .claude/skills/verify/scripts/browser.py stop "$CAD_BROWSER"
docker ps -a --filter label=cad.sandbox
pgrep -fl "$PWD/.venv/bin/python.*(-m cad\.server|bin/cad-server)"
```

- `stop` closes Chromium and ends the daemon, and prints `browser stopped: pid <pid>, <n> pages`. If it says the daemon is still running, `kill` that pid only.
- Each build and check removes its own container. `cad.sandbox` labels only sandbox containers, so removing what the second command lists is safe.
- The third command lists servers from this checkout. Stop only the pids this run started. Never `pkill` by name.
- Keep `$EVIDENCE`. It is the proof.

## Helpers

- `scripts/browser.py start|set|status|stop <dir>` and the opener `<dir>/bin/open <url>`: the person in a real browser. Use it for every proof of the confirmation page.
- `scripts/human.py <url>`, with `CAD_HUMAN_LOG=<path>`: a headless person over plain HTTP. Use it only where a browser cannot help: the brief-set eval (`evals/briefs/`), which runs many sessions in parallel, and the HTTP probes a browser cannot make, a GET with no or a wrong token and a replayed POST (see [Briefs](features/briefs.md)).
- `scripts/claude_session.py [--model <alias>] [--opener <program>] [--home <dir> | --real-home] "<prompt>" <transcript.json>`: a headless Claude Code session. `--home` overrides `$CAD_HOME`. `--real-home` uses your own `HOME`, only when the operator asks.

Feature recipes: [features/README.md](features/README.md).
