# Agreement between the scorecard and the bake-off grader

`agree.py` checks that the scorecard for a variant says the same thing as `grade.py` from commit `142404a` about the same STEP. It reads only what the server stored. The model never computes a verdict.

## The rule

The rule is `agree_rule` in `evals/bakeoff/agree.py`, fixed before any run.

- `closed_solid` passes exactly when `grade.py`'s category is not `no_output` or `invalid_solid`. The categories `bbox`, `volume` and `features` compare against a part's reference STEP, so they count as a valid solid.
- When both call the solid valid, the scorecard volume differs from `grade.py`'s volume by at most 0.01 mm3, and each sorted extent differs by at most 0.002 mm. A difference equal to the limit agrees, with 1e-9 of slack for float error.
- A variant with no scorecard never agrees.
- A scorecard whose `closed_solid` is `unknown` never agrees, because the checks did not finish (for example the check container timed out). That holds even when `grade.py` finds no output.

## What each side measures

- The scorecard side is `closed_solid`, the `mass` volume, and the sorted extents from the `sorted_extent:*` measures of the `extents` check. `agree.py` does not measure the BREP itself. It refuses a row when the scorecard's `brep_sha256`, or its `step` hash, does not match the stored file, and it takes no extents from a scorecard whose `extents` check is not `pass`.
- `extents` builds its box with `BRepBndLib.AddOptimal_s(shape, box, False, False)`, from the geometry and with no tolerance gap, which is the call `grade.py` makes. The default `BRepBndLib.Add_s` adds 1e-7 mm to each side, which is far below the 0.002 mm tolerance, but `AddOptimal_s` is used so the two sides measure the same box.
- The `grade.py` side is its category, volume and extents for the stored `result.step`. `extents` measures the BREP and `grade.py` the STEP derived from it, so a row also shows that the STEP export keeps the box.

## Reproduce

```
uv run python evals/bakeoff/agree.py             # Claude Code on Sonnet builds and scores the 10 briefs
uv run python evals/bakeoff/agree.py --replay    # the 60 stored build123d attempts, no model call
uv run python evals/bakeoff/agree.py --replay --attempt 0 --only opus/u_bracket/0   # one row
```

A live run starts each session with `claude_session.py`, which runs it from an empty directory outside the repo with `--tools ""`, so only the cad tools exist. A session that can reach or calls any other tool fails its row. A session costs about 0.04 USD.

A replay rewrites the final `export_step(shape, "out.step")` line of each stored script to `result = shape`, and builds each attempt into a fresh store.

## Result

Live, run 1 and run 2: 10/10 agree both times. Run 1 cost 0.401 USD. Run 3, with the scorecard side reading the `extents` check instead of measuring the BREP itself: 10/10 agree, 0.384 USD.

Replay: 59/60 agree, again after the `extents` change. The replay result is 59/60, with one accepted exception.

### Accepted exception: `sonnet/shaft_collar/0`

- The `closed_solid` check fails with "1 edges are used by more than two faces".
- `grade.py` passes the same part. It only counts solids and runs `BRepCheck_Analyzer`, so it cannot see a non-manifold edge.
- The defect is in the bake-off's stored `out0.step` for that attempt, so the edge comes from the script's geometry and not from the sandbox. Run `cad.checks.container.kernel.ocp_kernel().edge_uses` on `grade.load_step` of that file, taken from `142404a:proto/kernel-bakeoff/runs/build123d/sonnet/shaft_collar/0/out0.step`. It reports `EdgeUses(free=0, over_used=1)`, while `grade.py` returns `pass`. The same part from `sonnet/shaft_collar/1` reports `over_used=0`.
- The volume is 3589.62 mm3, against 3589.16 mm3 for the other two `shaft_collar` attempts that agree.
- The operator accepted 59/60 on 2026-11-07. `grade.py` and the rule are unchanged, and `agree.py` has no special case for this attempt, so `agree.py --replay` still prints `59/60 agree` and exits 1.

## Live run 1 (10/10 agree)

Reproduce one row with `uv run python evals/bakeoff/agree.py --only plate`.

| Run | closed_solid | Scorecard volume (mm3) | Scorecard extents (mm) | grade.py category | grade.py volume (mm3) | grade.py extents (mm) | Verdict |
|---|---|---|---|---|---|---|---|
| plate | pass | 29509.72 | 6.000 x 50.000 x 100.000 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | agree |
| l_bracket | pass | 6684.86 | 30.000 x 40.000 x 40.000 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | agree |
| motor_plate | pass | 19126.18 | 6.000 x 60.000 x 60.000 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | agree |
| spur_gear | pass | 17246.53 | 10.000 x 51.980 x 51.980 | pass | 17246.53 | 10.000 x 51.980 x 51.980 | agree |
| hex_spacer | pass | 3511.93 | 10.000 x 25.000 x 25.000 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | agree |
| shaft_collar | pass | 3589.16 | 10.000 x 25.000 x 25.000 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | agree |
| gusset | pass | 3646.64 | 4.000 x 45.757 x 45.757 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | agree |
| u_bracket | pass | 9572.74 | 30.000 x 40.000 x 50.000 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | agree |
| bearing_block | pass | 24736.73 | 20.000 x 40.000 x 40.000 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | agree |
| arm | pass | 49489.86 | 6.000 x 40.000 x 290.000 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | agree |

## Replay (59/60 agree)

Reproduce one row with `uv run python evals/bakeoff/agree.py --replay --only sonnet/shaft_collar/0`.

| Run | closed_solid | Scorecard volume (mm3) | Scorecard extents (mm) | grade.py category | grade.py volume (mm3) | grade.py extents (mm) | Verdict |
|---|---|---|---|---|---|---|---|
| opus/arm/0 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | agree |
| opus/arm/1 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | agree |
| opus/arm/2 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | agree |
| opus/bearing_block/0 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | agree |
| opus/bearing_block/1 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | agree |
| opus/bearing_block/2 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | agree |
| opus/gusset/0 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | agree |
| opus/gusset/1 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | agree |
| opus/gusset/2 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | agree |
| opus/hex_spacer/0 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | agree |
| opus/hex_spacer/1 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | agree |
| opus/hex_spacer/2 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | agree |
| opus/l_bracket/0 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | agree |
| opus/l_bracket/1 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | agree |
| opus/l_bracket/2 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | agree |
| opus/motor_plate/0 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | agree |
| opus/motor_plate/1 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | agree |
| opus/motor_plate/2 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | agree |
| opus/plate/0 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | agree |
| opus/plate/1 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | agree |
| opus/plate/2 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | agree |
| opus/shaft_collar/0 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | agree |
| opus/shaft_collar/1 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | agree |
| opus/shaft_collar/2 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | agree |
| opus/spur_gear/0 | pass | 17250.05 | 10.000 x 52.000 x 52.000 | pass | 17250.05 | 10.000 x 52.000 x 52.000 | agree |
| opus/spur_gear/1 | pass | 17250.44 | 10.000 x 52.000 x 52.000 | pass | 17250.44 | 10.000 x 52.000 x 52.000 | agree |
| opus/spur_gear/2 | pass | 17250.32 | 10.000 x 52.000 x 52.000 | pass | 17250.32 | 10.000 x 52.000 x 52.000 | agree |
| opus/u_bracket/0 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | agree |
| opus/u_bracket/1 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | agree |
| opus/u_bracket/2 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | agree |
| sonnet/arm/0 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | agree |
| sonnet/arm/1 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | agree |
| sonnet/arm/2 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | pass | 49489.86 | 6.000 x 40.000 x 290.000 | agree |
| sonnet/bearing_block/0 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | agree |
| sonnet/bearing_block/1 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | agree |
| sonnet/bearing_block/2 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | pass | 24736.73 | 20.000 x 40.000 x 40.000 | agree |
| sonnet/gusset/0 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | agree |
| sonnet/gusset/1 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | agree |
| sonnet/gusset/2 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | pass | 3646.64 | 4.000 x 45.757 x 45.757 | agree |
| sonnet/hex_spacer/0 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | agree |
| sonnet/hex_spacer/1 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | agree |
| sonnet/hex_spacer/2 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | pass | 3511.93 | 10.000 x 25.000 x 25.000 | agree |
| sonnet/l_bracket/0 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | agree |
| sonnet/l_bracket/1 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | agree |
| sonnet/l_bracket/2 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | pass | 6684.86 | 30.000 x 40.000 x 40.000 | agree |
| sonnet/motor_plate/0 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | agree |
| sonnet/motor_plate/1 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | agree |
| sonnet/motor_plate/2 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | pass | 19126.18 | 6.000 x 60.000 x 60.000 | agree |
| sonnet/plate/0 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | agree |
| sonnet/plate/1 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | agree |
| sonnet/plate/2 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | pass | 29509.72 | 6.000 x 50.000 x 100.000 | agree |
| sonnet/shaft_collar/0 | fail | - | - | pass | 3589.62 | 10.000 x 25.000 x 25.000 | DISAGREE |
| sonnet/shaft_collar/1 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | agree |
| sonnet/shaft_collar/2 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | pass | 3589.16 | 10.000 x 25.000 x 25.000 | agree |
| sonnet/spur_gear/0 | pass | 17513.15 | 10.000 x 52.000 x 52.000 | pass | 17513.15 | 10.000 x 52.000 x 52.000 | agree |
| sonnet/spur_gear/1 | pass | 17246.16 | 10.000 x 51.980 x 51.980 | pass | 17246.16 | 10.000 x 51.980 x 51.980 | agree |
| sonnet/spur_gear/2 | pass | 17248.22 | 10.000 x 52.000 x 52.000 | pass | 17248.22 | 10.000 x 52.000 x 52.000 | agree |
| sonnet/u_bracket/0 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | agree |
| sonnet/u_bracket/1 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | agree |
| sonnet/u_bracket/2 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | pass | 9572.74 | 30.000 x 40.000 x 50.000 | agree |
