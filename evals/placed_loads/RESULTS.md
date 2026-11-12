# Placed loads, build step 1, as measured

Printed by `evals/placed_loads/measure.py table` on 2026-11-12, from one run of each command below, on the build image `cad-sandbox:8a7e4a0613e8` and the analysis image `cad-analysis:5c4ce3c9a3cd`. The corpus settings are PLA (E 2300 MPa, ν 0.34, yield 51 MPa), 20 N, and a 2 mm deflection limit. The design note [fea-agent-placed-loads.md](../../docs/design/fea-agent-placed-loads.md), "Build step 1, as measured", says what the tables mean.

```
uv run python evals/placed_loads/measure.py faces faces.jsonl
uv run python evals/placed_loads/measure.py solve solve.jsonl
uv run python evals/placed_loads/measure.py table faces.jsonl solve.jsonl
```

The tables, in order: what code placement decides, explorer order in both images and after a turn, the surface share of each reviewed or described candidate, the mirror gate's candidates, and the curved faces on the stuck parts.

| Placement | Check verdict | Max displacement mm | Safety factor | Deflection at most 2 mm | Candidates | Solve s | Reason |
|---|---|---|---|---|---|---|---|
| equal_angle | pass | 1.90 | 3.84 | pass | 2 | 15 |  |
| sb_gusset long edge | pass | 0.96 | 5.01 | pass | 1 | 7 |  |
| sb_gusset short edge | unknown | 3.87 |  | unknown | 2 | 18 | max_displacement 3.86995 mm is over 5% of the part's 62.2254 mm extent, so a linear analysis does not hold |
| sb_gusset edge not said | unknown | 3.87 |  | unknown | 3 | 24 | max_displacement 3.86995 mm is over 5% of the part's 62.2254 mm extent, so a linear analysis does not hold |

| Part | Faces | Build = analysis | Max area diff | Max centroid diff mm | Turned keeps order | Max turned centroid diff mm | Placement indices kept |
|---|---|---|---|---|---|---|---|
| cantilever_bar | 6 | yes | 0.0e+00 | 0.0e+00 | yes | 6.4e-14 | no placement |
| l_plain | 8 | yes | 0.0e+00 | 0.0e+00 | yes | 1.3e-13 | no placement |
| l_holes | 10 | yes | 0.0e+00 | 0.0e+00 | yes | 8.5e-14 | no placement |
| l_gusset | 18 | yes | 0.0e+00 | 0.0e+00 | yes | 2.3e-13 | no placement |
| l_filleted | 14 | yes | 0.0e+00 | 0.0e+00 | yes | 2.5e-13 | no placement |
| u_bracket | 14 | yes | 0.0e+00 | 0.0e+00 | yes | 1.1e-13 | no placement |
| shelf_web | 13 | yes | 0.0e+00 | 0.0e+00 | yes | 4.7e-13 | no placement |
| hook | 12 | yes | 0.0e+00 | 0.0e+00 | yes | 8.0e-14 | no placement |
| plate_boss | 12 | yes | 0.0e+00 | 0.0e+00 | yes | 6.4e-14 | no placement |
| t_arm | 16 | yes | 0.0e+00 | 0.0e+00 | yes | 6.8e-14 | no placement |
| t_arm_flat_end | 16 | yes | 0.0e+00 | 0.0e+00 | yes | 4.3e-14 | no placement |
| i_beam_arm | 25 | yes | 0.0e+00 | 0.0e+00 | yes | 1.3e-13 | no placement |
| truss_arm | 22 | yes | 0.0e+00 | 0.0e+00 | yes | 6.4e-14 | no placement |
| square_tab | 6 | yes | 0.0e+00 | 0.0e+00 | yes | 1.2e-13 | no placement |
| equal_angle | 8 | yes | 0.0e+00 | 0.0e+00 | yes | 6.2e-14 | yes |
| sb_gusset | 9 | yes | 0.0e+00 | 0.0e+00 | yes | 6.4e-14 | NO |
| sb_arm | 32 | yes | 0.0e+00 | 0.0e+00 | yes | 8.0e-14 | no placement |
| sb_motor_plate | 11 | yes | 0.0e+00 | 0.0e+00 | yes | 1.1e-13 | no placement |
| sb_l_bracket | 12 | yes | 0.0e+00 | 0.0e+00 | yes | 6.4e-14 | no placement |
| i_beam_flat | 18 | yes | 0.0e+00 | 0.0e+00 | yes | 1.3e-13 | no placement |
| shelf | 11 | yes | 0.0e+00 | 0.0e+00 | yes | 2.9e-13 | no placement |
| rail_hook | 10 | yes | 0.0e+00 | 0.0e+00 | yes | 6.7e-14 | no placement |
| clamp | 10 | yes | 0.0e+00 | 0.0e+00 | yes | 1.1e-13 | no placement |
| plate | 6 | yes | 0.0e+00 | 0.0e+00 | yes | 8.1e-14 | no placement |

| Part | Case | Candidates | Largest support share | Largest load share |
|---|---|---|---|---|
| cantilever_bar | reviewed | 2 | 2.3% | 2.3% |
| l_plain | reviewed | 2 | 14.4% | 14.4% |
| l_holes | reviewed | 1 | 1.3% | 1.4% |
| l_gusset | reviewed | 1 | 2.1% | 1.2% |
| l_filleted | reviewed | 1 | 1.4% | 1.1% |
| u_bracket | reviewed | 1 | 19.9% | 0.7% |
| shelf_web | reviewed | 1 | 0.7% | 0.6% |
| hook | reviewed | 1 | 1.8% | 0.0% (band) |
| hook | Holes(2, 4), OnFarthest(inner curve 20), across hole axis | 1 | 1.8% | 11.1% |
| hook | Holes(2, 4), OnFarthest(inner curve), Away | 1 | 1.8% | 11.1% |
| plate_boss | reviewed | 1 | 3.6% | 2.9% |
| t_arm | reviewed | 1 | 1.0% | 0.9% |
| t_arm_flat_end | reviewed | 2 | 14.0% | 14.0% |
| i_beam_arm | reviewed | 1 | 0.8% | 0.7% |
| truss_arm | reviewed | 1 | 1.2% | 0.6% |
| square_tab | reviewed | 4 | 3.4% | 3.4% |
| equal_angle | reviewed | unresolved | | |
| sb_gusset | reviewed | unresolved | | |
| sb_arm | reviewed | unresolved | | |
| sb_arm | Each(hole 28), OnFarthest(hole 28), across hole axis | 2 | 2.3% | 2.3% |
| sb_motor_plate | reviewed | 1 | 2.8% | 4.9% |
| sb_l_bracket | reviewed | unresolved | | |
| sb_l_bracket | InOneFlatFace(2, 5.1), far end, any way | 2 | 1.8% | 21.9% |
| i_beam_flat | reviewed | 2 | 0.9% | 0.9% |
| shelf | Holes(3, 5), OnLargestFlat(middle), Into | 1 | 0.4% | 1.0% |
| shelf | InOneFlatFace(3, 5), OnLargestFlat(middle), Into | 1 | 0.4% | 1.0% |
| rail_hook | Each(inner curve), OnFarthest(inner curve), Away | 2 | 7.1% | 7.1% |
| clamp | Facing, OnOpposite, Into | 2 | 9.6% | 9.6% |
| clamp | Facing, OnOpposite(middle), Into | 2 | 9.6% | 0.3% |
| plate | FlatEnd, OnLargestFlat(middle), Into | 4 | 1.6% | 1.3% |
| plate | EndOf(middle), OnLargestFlat(middle), Into | 4 | 6.3% | 1.3% |

Largest share of any reviewed or described region: 21.9%.

| Placement | From code | Mirror adds | Total | Over 4 | Support share | Load share | Surfaces |
|---|---|---|---|---|---|---|---|
| equal_angle | 1 | 1 | 2 | no | 22.2% | 1.8% | flat |
| sb_gusset long edge | 1 | 0 | 1 | no | 8.4% | 0.7% | flat, round |
| sb_gusset short edge | 1 | 1 | 2 | no | 5.9% | 1.0% | flat, round |
| sb_gusset edge not said | 2 | 1 | 3 | no | 8.4% | 1.0% | flat, round |

| Stuck part | Faces | Curved faces |
|---|---|---|
| cantilever_bar | 6 | 0 |
| l_plain | 8 | 0 |
| l_holes | 10 | 0 |
| l_filleted | 14 | 0 |
| hook | 12 | 0 |
| t_arm | 16 | 0 |
| t_arm_flat_end | 16 | 0 |
| truss_arm | 22 | 0 |
| equal_angle | 8 | 0 |
| sb_gusset | 9 | 0 |
| sb_arm | 32 | 0 |
| sb_l_bracket | 12 | 0 |

Stuck parts with any curved face: 0 of 12.
