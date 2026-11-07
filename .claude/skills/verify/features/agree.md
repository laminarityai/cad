# Agree

`evals/bakeoff/agree.py` checks that the scorecard and the bake-off grader (`evals/bakeoff/grade.py`, unchanged from commit `142404a`) agree on the same variants. The rule is `agree_rule` in that file, and `evals/bakeoff/AGREEMENT.md` records the last run.

## Sub-features

- `agree-live` makes Claude Code on Sonnet build and score each of the 10 bake-off briefs through the cad tools, then compares the stored scorecard with `grade.py` on the stored STEP. A row also fails when the final reply states a volume, mass, area or bounding box that no `score_variant` result returned (`evals/bakeoff/reply.py`). It prints one row per brief and `10/10 agree`.
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
- The reply check counts a number from `build_variant`'s `output` as unchecked, because that field is what the agent's own code printed.
- The reply check reads the measured quantities and the formula thresholds of each `score_variant` result through `Scorecard`, and compares a reply number with them in the reply's own unit. Counts, hashes and ids in the scorecard are never matched.
- A label ("not a check", "not from a check", "not checked", "unchecked", "not measured") covers a number or a phrase such as "my own arithmetic" only in its own clause, or in the next clause of the same sentence when the label is all that clause says. Commas, semicolons, colons, brackets, "and", "but" and "while" end a clause. A label never excuses "I confirmed", "I verified", "matches my" or "consistent with the scorecard".
- Known limits of the reply check, each a strict xfail in `tests/evals/test_reply_check.py`:
  - It reads mm, cm, in, g, kg and their squares, cubes and densities only. It misses ml, lb, in³ and spelled-out units such as "cubic millimetres".
  - It misses a length with no measurement word, such as "101 mm long, 50 mm wide and 6.2 mm thick".
  - A zero passes when the interference check measured a common volume of 0 mm³, which it does for every single-body part.
  - Some honest replies fail: "I verified the scorecard was stored", "which matches my expectation", "I computed no geometry", a brief dimension in a bounding-box sentence, and a brief hole diameter in a volume sentence.
- The live gate for the reply check is the red agree row of commit `69c1952`, not a unit test. The unit tests use recorded transcripts.
- The scorecard has no extents. `agree.py` measures the stored `result.brep` that the scorecard's `brep_sha256` names.
