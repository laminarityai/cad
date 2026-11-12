---
name: verify
description: Drive the cad MCP server the way a client does (one scripted stdio call with `cad-call`, or a headless Claude Code session with `claude_session.py`) and drive its confirmation page in a real Chromium (`browser.py`). Use it to prove any change to a tool, the server, the confirmation page, or what an MCP client sees.
---

# Verify cad

What a user touches today:

- **The MCP server over stdio** (`uv run cad-server`). Drive it with `cad-call` (one tool call) or `claude_session.py` (a real Claude Code session).
- **The confirmation page** in the signed-in web app. `ask_to_confirm` hands the server's opener a local sign-in link, which lands on `/projects/<project_id>/confirm` with a session cookie. Drive it in a real browser with `browser.py`, and its refusals with `human.py` and `curl`: [features/phase-4/hosted-confirmation.md](features/phase-4/hosted-confirmation.md).

- **The MCP server over HTTP** (`uv run cad-http`), with accounts. Drive it with `curl` and `cad-call --url`: [features/hosted-mcp.md](features/hosted-mcp.md).
- **The web app** at `/app` on `cad-http`: the project workspace with the chat, the viewers, the scorecards and the Auto run status. Drive it in a real browser with `browser.py web shot` and `browser.py web walk`: [Chat](features/phase-4/chat.md), [Web shell](features/phase-4/web-shell.md) and [Auto](features/phase-4/auto.md).

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
| `cad-call --url` on the warm `cad-http` | about 3 s once to start the server, then about 0.5 s per call, no Docker, no model | a tool's result, a refusal, stored files |
| stdio `cad-call` | about 2 to 8 s per call, because each call starts a server | a claim about the stdio server itself |
| `cad-call build_variant`, `score_variant`, `cad-sandbox run-checks` | one container, about 20 s for new code. The same code in the same `CAD_HOME` is a store hit and starts none | a build, a check, a scorecard |
| `browser.py` | one Chromium per run: about 13 s on the first launch after install, 2 s after that. Each page adds about 2 s | what the person sees and does on the confirmation page |
| `claude_session.py` | a live model session: money and 30 s to several minutes | what the agent does: which tools it calls, what it says |

Confirming a brief needs no model: create the brief, propose and call `ask_to_confirm` with `cad-call`, with the browser as the person (see Drive). Use a live session only when the claim is about the agent's behaviour. Each feature file in [features/README.md](features/README.md) lists its cheapest proof.

## Launch

```
uv sync --frozen
uv run playwright install chromium
uv run cad-sandbox build-image
uv run cad-reader build-image
uv run python .claude/skills/verify/scripts/browser.py start "$CAD_BROWSER"
```

- `playwright install chromium` is needed once per machine. It deletes browsers of other Playwright versions that it thinks are unused.
- `build-image` is needed only for recipes that start a container. It prints `sandbox image cad-sandbox:<tag> is current` and then the same line for `cad-analysis:<tag>`, or builds a missing image, which takes minutes. With Docker down it prints the cause and exits 1. `cad-reader build-image` does the same for `cad-reader:<tag>`, the image that reads a researched PDF.
- `browser.py start` is needed only for recipes that open the confirmation page. It returns when the browser answers, and prints `browser ready: {...}` and `opener: <path>`. Running it again on the same directory reuses the running browser.

Each stdio `cad-call` and each Claude Code session starts its own server and stops it. `uv run cad-http` is the long-running server. `cad-call --url` talks to it, and so do the web app and `curl`.

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

### cad-call on a warm server (the default)

Start one `cad-http` for the run and send every call to it. The token's audience is the `/mcp` URL, so `cad-token` needs the same `--url`:

```
HOME="$CAD_HOME" uv run cad-http --root "$EVIDENCE/root" --port 8791 --opener "$CAD_BROWSER/bin/open" > "$EVIDENCE/http.log" 2>&1 & echo $! > "$EVIDENCE/http.pid"
export CAD_URL=http://127.0.0.1:8791 CAD_TOKEN=$(uv run cad-token --root "$EVIDENCE/root" agent user_walk --url http://127.0.0.1:8791)
uv run cad-call --url "$CAD_URL/mcp" --token "$CAD_TOKEN" <tool> '<json args>'
```

Its opener is the browser's, so `ask_to_confirm` goes to the scripted person. Stop it when the run ends with `kill $(cat "$EVIDENCE/http.pid")`: `uv` passes the signal on to the server. A three-call walk took 1.3 s here against 6.7 s over stdio, plus about 3 s to start the server.

### cad-call over stdio

Use it only when the claim is about the stdio server, as `uv run verify --only app` does:

```
HOME="$CAD_HOME" uv run cad-call <tool> '<json args>'
```

It prints the MCP result as JSON and exits 1 when the result is an error and 2 when the arguments are not a JSON object. `server_info` lists the agent's tools in `structuredContent.tools`. `jq -Rs '{code: .}' < <file>.py` turns a build123d file into the arguments `build_variant` takes. The stdio client passes the server only `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM` and `USER`.

### The confirmation page in a real browser

`browser.py start` writes `$CAD_BROWSER/bin/open`, the opener. The server runs it with the sign-in link, and it hands the link to the one running Chromium, which follows the link's redirect and keeps the session cookie. For each page n, the browser reads every section by its heading, saves `page-<n>.aria.yml` (the ARIA snapshot), types an edit if one is set, saves `page-<n>-before.png`, presses `Confirm` or `Decline all`, and saves `page-<n>-after.png` (the reply page). It appends JSON lines to `$CAD_BROWSER/browser.jsonl`:

- `{"page": n, "step": "page", "status": 200, "path": "/projects/<project_id>/confirm", "heading": ..., "sections": [{"heading", "brief", "quotes", "quotes_in_brief"}], "quotes_in_brief": true}`
- `{"page": n, "step": "edit", "shown": "150 g", "typed": "120 g", "fields": 1}`, only when an edit is set
- `{"page": n, "step": "confirm" | "decline", "status": 200, "said": "Recorded. You confirmed 1 and declined 0 on this page. ..."}`
- `{"page": n, "spent_token": "<person JWT>"}`
- `{"page": n, "error": "..."}` for any failure, with the JWT replaced by `<token>`, because the server discards the opener's output

Set how the person answers. The settings hold for every later page:

```
uv run python .claude/skills/verify/scripts/browser.py set "$CAD_BROWSER" answer=decline
uv run python .claude/skills/verify/scripts/browser.py set "$CAD_BROWSER" answer=confirm "edit=150 g=120 g"
uv run python .claude/skills/verify/scripts/browser.py set "$CAD_BROWSER" edit= delay=1
uv run python .claude/skills/verify/scripts/browser.py set "$CAD_BROWSER" answer=confirm "decline_item=A check the agent wrote"
```

`edit=<shown>=<typed>` types `<typed>` into each `Change to` field whose placeholder is `<shown>`. `delay` is the seconds before answering (default 1). A declined page gets the note `scripted person declined`. `decline_item=<text>` ticks `Decline this item` in each section whose heading holds `<text>`, writes the note `scripted person declined this item` and presses `Confirm`, so the rest of the page is confirmed. `decline_item=` turns it off.

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
uv run verify --all
```

CI runs this on every PR, so run it here only to debug. [run-tests](../run-tests/SKILL.md) says which steps to run on this laptop, and `src/cad/verify/steps.py` lists every step. The `app` step fails unless `server_info` reports `git rev-parse HEAD`. A dirty tree prints `dirty=True` and does not fail.

## Evidence

Everything goes under `$EVIDENCE`: `cad-call` output as `<slug>.json`, transcripts, `$CAD_BROWSER/` (log, ARIA snapshots, screenshots) and `$CAD_HOME/.cad/` (the stores the run wrote).

- Prove the user's path. A claim about what the agent does needs a transcript. A claim about the page needs the browser's screenshots and log, not an HTTP probe.
- Capture the action and the result, then read the side effect from a second view: `list_requirements` after a page answer, the variant directory after a build, `scorecard` after a score.
- The person JWT from `spent_token` must not appear in any transcript: `grep -c "<spent_token>" <transcript>` prints `0`.

## Cleanup

```
uv run python .claude/skills/verify/scripts/browser.py stop "$CAD_BROWSER"
docker ps -a --filter label=cad.sandbox
pgrep -fl "$PWD/.venv/bin/python.*(-m cad\.server|bin/cad-server|bin/cad-http)"
```

- `stop` closes Chromium and ends the daemon, and prints `browser stopped: pid <pid>, <n> pages`. If it says the daemon is still running, `kill` that pid only.
- Each build and check removes its own container. `cad.sandbox` labels only sandbox containers, so removing what the second command lists is safe.
- The third command lists servers from this checkout. Stop only the pids this run started. Never `pkill` by name.
- Keep `$EVIDENCE`. It is the proof.

## Helpers

- `scripts/browser.py start|set|status|stop <dir>` and the opener `<dir>/bin/open <url>`: the person in a real browser. Use it for every proof of the confirmation page.
- `scripts/human.py <sign-in link>`, with `CAD_HUMAN_LOG=<path>`: a headless person over plain HTTP, with a cookie jar. Use it only where a browser cannot help: the brief-set eval (`evals/briefs/`), which runs many sessions in parallel, and the HTTP probes a browser cannot make, a GET with no session and a replayed POST (see [Briefs](features/briefs.md)). Other refusals are `curl` probes: [Hosted confirmation](features/phase-4/hosted-confirmation.md).
- `scripts/geometry.py <dir> <part.py>...`: build and score parts through the MCP server, read each mesh through the person-only `geometry` operation, compare its volume with the `mass` check, and screenshot it in three-cad-viewer. See [Geometry](features/geometry.md).
- `scripts/browser.py web shot|watch|walk ...` (in `scripts/web_drive.py`): a signed-in person on the web app of a local `cad-http`, signed in with the `__session` cookie its `local-issuer.pem` signs. `shot` writes a screenshot and the ARIA tree of one route. `watch` follows the check lines of the option on screen while something else scores it (see Web shell). `walk` (`scripts/web_walk.py`) is one live walk of the project workspace. `download <run> <out> [--url URL] [--account ID] [--project ID]` (`scripts/web_download.py`) opens the Download menu on the option on screen, shoots it, saves STEP, STL and 3MF, and checks them against the scorecard: see [Download](features/download.md). See [Web shell](features/phase-4/web-shell.md) and [Chat](features/phase-4/chat.md).
- `scripts/clerk_session.py <out> expired|signed-out|double`: the Clerk session expiry repro for the confirmation page, against a stand-in Clerk Frontend API. See [Hosted confirmation](features/phase-4/hosted-confirmation.md).
- `scripts/claude_session.py [--model <alias>] [--opener <program>] [--home <dir> | --real-home] "<prompt>" <transcript.json>`: a headless Claude Code session. `--home` overrides `$CAD_HOME`. `--real-home` uses your own `HOME`, only when the operator asks.

Feature recipes: [features/README.md](features/README.md).
