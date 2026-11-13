# Brief set

`evals/briefs/run.py` runs every brief in the private set (`~/cad-evals/briefs/`, one `<id>.yaml` each) through a headless Claude Code session, then traces the scorecards the session was shown. One run records the phase 2 exit (every number on every scorecard traces to a confirmed source), the friction numbers (#50) and the coverage baseline (#49).

Per brief it starts `claude_session.py` with `--opener .claude/skills/verify/scripts/human.py` and a fresh `--home` under `<out>/<id>/home`, so the server's briefs, projects and variants stay in that run's own directory. The session sees only the `brief` field of the YAML, never the `grader` block, and the prompt adds one sentence of framing. Afterwards it runs the tracer (`evals/briefs/trace_store.py`) over that run's transcript and home with `--require-judged` semantics, and writes `<out>/<id>/result.json`.

## The in-process driver

`--driver inprocess` runs the chat agent in the runner's process, the way the web app does, and stops at the Auto stop instead of tracing scorecards. It writes `<out>/<id>/auto.json` (the stop, its `Bounds`, the revisions, the run that holds the conversation, the variants and the container runs the account's meter holds), `events.json` (the stream) and `human.jsonl`, and `<out>/auto-summary.json`. `--model scripted` (the default) plays the grader's requirements and builds nothing, so every brief stops with `agent_asked` or `conflict` in about a second. `--model <anthropic id>` runs a live agent that sees only the brief. A grader's `expect` block (`stop`, `within_revisions`, `names`) says what a brief must do, and a brief without one passes when its run stops. Recipe: [Auto](phase-4/auto.md).

## Sub-features

- `brief-set-run` runs the set, up to `--jobs` briefs at once (default 3), and prints one line per brief and then the summary.
- `brief-set-resume` runs the same command again with the same `--out`. A brief with a finished `result.json` is skipped. A brief whose session failed, or that a kill left half done, runs again from a fresh home.
- `brief-set-only` runs a subset with `--only <id> ...`.

## How to get to it

Keep `--briefs` and `--out` outside the repo. Transcripts hold the brief text, and `summary.md` names untraced numbers.

```
uv run python evals/briefs/run.py --briefs ~/cad-evals/briefs --out ~/cad-evals/runs/<stamp> [--model sonnet] [--jobs 3] [--only <id> ...] [--timeout 1800] [--require-traced]
```

`--model` is the Claude Code alias for every session (default `sonnet`). The model that answered is recorded in each `result.json` and in `summary.md`. Preconditions are those of [Agree](./agree.md): Docker runs, `uv run cad-sandbox build-image` exits 0, and `claude` is logged in.

## What it writes

- `<out>/<id>/transcript.json`, `human.jsonl` (the scripted person's log) and `home/` (the session's stores).
- `<out>/<id>/result.json`: status, model, cost, turns, seconds, friction, and the trace.
- `<out>/summary.md` and `summary.json`: the overall numbers and one row per brief, rewritten from the result files on every run.

## The numbers

- Traced: the tracer passes over that brief's stores with `--require-judged`. After the session it reads every variant scored with a brief through the server's own `scorecard` operation (`readings.py`), which builds, runs and writes nothing, and traces each reading as a card. `result.json` and `summary.md` count the cards the session was shown, and their numbers, apart from the readings. Traced needs at least one card, every number resolved, no card with no brief, and every card awaiting confirmation followed by a card or reading that judges its variant against the same brief. A brief that is not traced lists each reason under `Untraced in <id>` in `summary.md`: failed cards, stale or unresolved numbers, a card still awaiting confirmation, a card with no brief, a reading the server refused, a tracer that failed, or no card. Agent measurements count as not verified (ADR-0008) and are listed in `result.json` under `agent_measurements`, apart from the untraced ones.
- Strict pass rate and coverage (#49) are the tracer's `track` numbers over the requirements on the server's reading of the last variant scored with a brief, the judged state the person sees after Confirm. With no variant scored with a brief, they come from the last scorecard a tool returned. The overall rates pool those requirements across briefs. A requirement passes strictly when a reviewed check decided it and the verdict is pass, and it is covered when a reviewed check decided it. The requirements are the ones the agent proposed and the scripted person confirmed, so a requirement the agent left out of its proposal is in neither number.
- Friction (#50): confirmation pages are the pages the scripted person opened (its `page` log entries), and `ask_calls` is how many times the agent called `ask_to_confirm`. Minutes run from the earliest stored brief in the session's home to the earliest signed job result's last write (the server stores no scorecard). The scripted person waits one second before it answers, so no reading time is in them.

## Gotchas

- A session that fails is `session_failed` in the summary, not untraced, and the exit code is 1. `--require-traced` makes the exit code 1 for any untraced brief too.
- Each session is a real model run. See `cost_usd` in `result.json`.
- `trace_store.trace_cards` is what the tracer and the driver share, and `transcript_cards.read_cards` takes the cards from a transcript. Run `evals/briefs/trace_store.py <out>/<id>/transcript.json --root <home>/.cad/variants --briefs-root <home>/.cad/briefs --projects-root <home>/.cad/projects --require-judged` to see the trace of the cards the session was shown. It reads nothing from the server, so a card scored before Confirm counts as awaiting unless a later card in the transcript judges its variant.
