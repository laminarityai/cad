# Agree

`evals/bakeoff/agree.py` checks that the scorecard and the bake-off grader (`evals/bakeoff/grade.py`, unchanged from commit `142404a`) agree on the same variants. The rule is `agree_rule` in that file, and `evals/bakeoff/AGREEMENT.md` records the last run.

## Sub-features

- `agree-live` makes Claude Code on Sonnet build and score each of the 10 bake-off briefs through the cad tools, then compares the stored scorecard with `grade.py` on the stored STEP. It prints one row per brief and `10/10 agree`.
- `agree-replay` builds and scores the 60 stored build123d attempts with no model call. It prints one row per attempt and a final `N/60 agree`.
- `agree-one` runs one row, with `--only <part>` (live) or `--only <model>/<part>/<sample>` (replay).
- `agree-first-attempt` replays attempt N of the runs that have it, with `--attempt N`.

## How to get to it (user POV)

- Run `uv run python evals/bakeoff/agree.py` or add `--replay`, in a terminal at the repo root.

## Driving it

Preconditions:

- The preconditions of [Build variant](./build-variant.md): Docker Desktop runs and `uv run cad-sandbox build-image` exits 0.
- `claude` is logged in. A live run costs about 0.4 USD for 10 parts.

- **Live.** Run `uv run python evals/bakeoff/agree.py --out "$EVIDENCE/live" | tee "$EVIDENCE/agree-live.txt"`. The last line is `10/10 agree` and the exit code is 0. `$EVIDENCE/live/<part>.json` holds each Claude Code transcript, and the line before the last holds the total cost.
- **Replay.** Run `uv run python evals/bakeoff/agree.py --replay | tee "$EVIDENCE/replay.txt"`. It takes about 4 minutes.
- **One row.** Run `uv run python evals/bakeoff/agree.py --replay --attempt 0 --only opus/u_bracket/0`. Both sides report a valid solid with a volume of 9486.90 mm^3, and `grade.py` names the category `features`.

## Cleanup

A replay builds into a temporary store, `agree-store-*` under the temp directory, and removes it at the end. A live run uses `~/.cad/variants`.

## Gotchas

- A live row with no scored variant is a disagreement, not a skipped row.
- A scorecard whose `closed_solid` is `unknown` (the checks did not finish) never agrees, even when `grade.py` also finds no output.
- `sonnet/shaft_collar/0` disagrees in a replay. `closed_solid` fails on an edge used by more than two faces, and `grade.py` has no such test.
- The scorecard has no extents. `agree.py` measures the stored `result.brep` that the scorecard's `brep_sha256` names.
