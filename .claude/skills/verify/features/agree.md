# Agree

`evals/bakeoff/agree.py` checks that the scorecard and the bake-off grader (`evals/bakeoff/grade.py`, unchanged from commit `142404a`) agree on the same variants. The rule is `agree_rule` in that file, and `evals/bakeoff/AGREEMENT.md` records the last run.

## Sub-features

- `agree-live` makes Claude Code on Sonnet build and score each of the 10 bake-off briefs through the cad tools, then compares the stored scorecard with `grade.py` on the stored STEP. It prints one row per brief and `10/10 agree`.
- `agree-replay` builds and scores the 60 stored build123d attempts with no model call. It prints one row per attempt and a final `N/60 agree`.
- `agree-one` runs one row, with `--only <part>` (live) or `--only <model>/<part>/<sample>` (replay).
- `agree-first-attempt` replays attempt N of the runs that have it, with `--attempt N`.
- `reply-report` runs `evals/bakeoff/reply.py` over saved transcripts. For each final reply it lists the numbers that match a `score_variant` result, the numbers no check returned (with or without a "not checked" label, and where each came from), and the phrases that present the agent's own arithmetic as confirmation. It exits 0 whatever it finds. It is a measurement, not a gate: `agree.py` never reads it.

## How to get to it (user POV)

- Run `uv run python evals/bakeoff/agree.py` or add `--replay`, in a terminal at the repo root.

## Driving it

Preconditions:

- The preconditions of [Build variant](./build-variant.md): Docker Desktop runs and `uv run cad-sandbox build-image` exits 0.
- `claude` is logged in. A live run costs about 0.4 USD for 10 parts.

- **Live.** Run `uv run python evals/bakeoff/agree.py --out "$EVIDENCE/live" | tee "$EVIDENCE/agree-live.txt"`. The last line is `10/10 agree` and the exit code is 0. `$EVIDENCE/live/<part>.json` holds each Claude Code transcript, and the line before the last holds the total cost.
- **Replay.** Run `uv run python evals/bakeoff/agree.py --replay | tee "$EVIDENCE/replay.txt"`. It takes about 4 minutes.
- **Reply report.** Run `uv run python evals/bakeoff/reply.py tests/evals/replies "$EVIDENCE/live"`. It prints one block per transcript. A transcript named `<part>.json` or `<part>_<anything>.json` is read against that part's brief.
- **One row.** Run `uv run python evals/bakeoff/agree.py --replay --attempt 0 --only opus/u_bracket/0`. Both sides report a valid solid with a volume of 9486.90 mm^3, and `grade.py` names the category `features`.

## Cleanup

A replay builds into a temporary store, `agree-store-*` under the temp directory, and removes it at the end. A live run uses `~/.cad/variants`.

## Gotchas

- A live row with no scored variant is a disagreement, not a skipped row. So is a row whose `claude_session.py` run failed, for example on a tool call outside cad.
- A scorecard whose `closed_solid` is `unknown` (the checks did not finish) never agrees, even when `grade.py` also finds no output.
- `sonnet/shaft_collar/0` disagrees in a replay. `closed_solid` fails on an edge used by more than two faces, and `grade.py` has no such test.
- The reply report matches phrases and units. The rule the server sends as its instructions and in the `score_variant` description (`RULE` in `src/cad/server/app.py`) is what enforces the behaviour. The report only measures how often replies follow it.
- The reply report counts a number from `build_variant`'s `output` as unchecked, because that field is what the agent's own code printed.
- The reply report reads only the `results` of each `score_variant` result: their measured quantities and formula thresholds. It compares a reply number with them in the reply's own unit. Counts, hashes and ids in the scorecard are never matched.
- A label ("not a check", "not from a check", "not checked", "unchecked", "not measured") covers a number only in its own clause, or in the next clause of the same sentence when the label is all that clause says. Commas, semicolons, colons, brackets, "and", "but" and "while" end a clause.
- Known misses of the reply report:
  - A paraphrased approval such as "you're good to go" is not reported. `tests/evals/test_reply_check.py` pins this miss.
  - It reads mm, cm, in, g, kg and their squares, cubes and densities only. It misses ml, lb, in³ and spelled-out units such as "cubic millimetres".
  - It misses a length with no measurement word, such as "101 mm long, 50 mm wide and 6.2 mm thick".
  - A self-computed number that equals a checked value within its rounding is reported as checked, for example "37 g" when the mass check measured 36.6 g, or "0 mm³" when the interference check measured a common volume of 0 mm³.
  - Some honest phrases are reported as confirmation, such as "I verified the scorecard was stored" and "which matches my expectation".
- `agree.py` reads the sorted extents from the `sorted_extent:*` measures of the scorecard's `extents` check. It no longer measures the BREP itself. It still refuses a row when the stored `result.brep` or `result.step` does not match the hash the scorecard names. `grade.py` measures the same box with `BRepBndLib.AddOptimal_s(shape, box, False, False)`, which is what `extents` uses.
