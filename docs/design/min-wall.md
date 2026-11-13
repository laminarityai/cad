# min_wall: the thinnest wall a person states a limit on

A person may write "walls at least 2 mm thick" or "no wall under 1.5 mm". ADR-0011 ("Walls the person states") says a team check decides that limit, with no default taken from a printer and no verdict on walls nobody stated. The `min_wall` check measures the thinnest wall of the part. A `measure_limit` on `min_wall:min_wall` holds it to the limit the person confirmed.

## What a wall is

A wall is the material between a face and the face across from it. Its thickness at a point is how far you go straight into the material from that point, at right angles to the face, until you come out through a face on the far side.

## The method

The check is `src/cad/checks/container/min_wall.py`. The rays are `src/cad/checks/container/kernel/ocp_walls.py`.

1. **A reading.** From a point on a face, a ray goes along the face's inward normal. It stops where it first comes out of the material. The reading counts only when the exit face looks back at the start within 60 degrees: the dot product of the ray and the exit face's outward normal is at least 0.5. A ray that comes out through a face turned further away is near a corner. It gives no reading. A ray that never comes out, or that the kernel cannot follow, makes the whole result unknown. The 60-degree rule is the one phase-3.md set for the deferred printability check.
2. **First grid.** Every face is sampled at 2 by 2 points in its parameter box. The thinnest reading bounds the spacing in step 3.
3. **Second grid.** Every face is sampled again, with points no farther apart than the thinnest first reading. The spacing is also no wider than the closest spacing at which the grid over all faces fits in 40,000 points. A face keeps at least 2 points each way.
4. **Refining.** At most 32 faces are refined, the ones whose thinnest point is within 1.5 times the thinnest reading. From each face's thinnest point, a compass search steps to a neighbour that reads thinner, and otherwise halves its step. It stops at a millionth of the face's parameter range.
5. **The value.** `min_wall` is the thinnest reading of all.

The check reads only the stored shape. It needs `closed_solid` to pass. Each face has its own `IntCurvesFace_Intersector` behind a tree of face bounding boxes, so a ray asks only the faces it passes near. `IntCurvesFace_ShapeIntersector` asks every face. On the 2019-face spur gear that cost 1.2 ms a ray (measured), about 155 s for the whole check (inferred).

## What it reads on the shapes a person might worry about

| Shape | Reading | Why |
| --- | --- | --- |
| Solid block 10 × 20 × 30 | 10 | Its thinnest dimension. |
| Rod 8 mm across, 30 long | 8 | Its diameter. |
| Knife edge, faces 7 degrees apart | about 1e-6 | A wall that thins to nothing. Any limit fails. |
| 2 mm plate whose top edge has a 1 mm round | 1.5 | Rays up from the bottom count until the round turns 60 degrees from the bottom face. Past that the exit is a corner. The plate thins to nothing only at a 90-degree edge. |
| A bore that touches the top face exactly | unknown | The boolean leaves an edge used by more than two faces, so `closed_solid` does not pass. On its own, a ray here never comes out (measured), which is also unknown. |

## Error bound

`ERROR_BOUNDS = {"min_wall": 0.001}`, a relative error. For an `at_least` limit L, the requirement passes when min_wall × 0.999 ≥ L. It fails when min_wall × 1.001 < L. Otherwise it is unknown within the check's stated error. A wall made exactly at the limit is unknown, so a variant must clear the limit by more than 0.1%.

The truth for each case follows from the shape by hand, under the same 60-degree rule. Each case was read twice through the real kernel: once as made, and once turned 0.7 rad about (1, 2, 3), moved, and with the faces listed back to front. The table gives the reading and the error of the worse run. `tests/checks/test_min_wall_walls.py` asserts the built cases are within the bound. The reference parts under `tests/sandbox/parts` were built with `build_variant`. Their plain runs were read in the analysis image `cad-analysis:5c4ce3c9a3cd`, and their turned runs on the host with the same OCP. `tests/checks/test_reference_parts.py` asserts `min_wall` passes on each.

Every case was measured again on 2026-11-13, when the ray cap went from 100,000 to 250,000. The reference parts were built from the same files in the build image `cad-sandbox:8a7e4a0613e8`. Every reading and error matched the earlier run, and the two large parts were added.

| Case | Truth (mm) | Read (mm) | Relative error |
| --- | --- | --- | --- |
| Box shell, 2 mm walls | 2 | 2.0000000 | 1.4e-14 |
| Tube, 1.5 mm wall | 1.5 | 1.5000000 | 4.3e-13 |
| Plate with a 0.8 mm rib | 0.8 | 0.8000000 | 2.2e-14 |
| Hole 0.6 mm from an edge (short, easy to miss) | 0.6 | 0.6000000 | 1.3e-12 |
| Wall tapered from 3 to 1 mm | 1 | 1.0000013 | 1.3e-6 |
| Crossed slots, 0.5 mm apart (short, easy to miss) | 0.5 | 0.5000000 | 2.8e-14 |
| Crossed holes, 0.4 mm apart (short, easy to miss) | 0.4 | 0.4000000 | 3.5e-12 |
| Bore 0.05 mm under the top | 0.05 | 0.0500000 | 1.8e-11 |
| 2 mm plate with a 1 mm round | 1.5 | 1.5000242 | 1.6e-5 |
| Plate 300 × 200 × 1 mm (large for its wall) | 1 | 1.0000000 | 4.3e-14 |
| Open box 250 × 200 × 100 mm, 1.5 mm walls (large for its wall) | 1.5 | 1.5000000 | 5.7e-14 |
| arm | 6 | 6.0000000 | 1.7e-13 |
| bearing_block | 5 − 2.55 = 2.45 | 2.4500000 | 4.8e-13 |
| gusset | 50 / (3√2) − 10 = 1.7851130 | 1.7851130 | 2.5e-13 |
| hex_spacer | 12.5 − 12.7 / √3 = 5.1676516 | 5.1676516 | 6.2e-15 |
| l_bracket | 3 | 3.0000000 | 9.6e-15 |
| motor_plate | 6 | 6.0000000 | 2.4e-15 |
| plate | 5.45 | 5.4500000 | 8.1e-16 |
| shaft_collar | 5 − 1.65 = 3.35 | 3.3500000 | 1.5e-13 |
| spur_gear | 2.1768501, the outline's 2016 segments cast exactly in 2D | 2.1768503 | 1.1e-7 |
| u_bracket | 2 | 2.0000000 | 1.4e-14 |

The worst error is 1.6e-5, on the round, where the search stops a little short of the 60-degree point. The bound is 60 times that. The cases include short walls that a grid misses: the crossed holes read 14 mm on a 4 × 4 grid per face (measured) and 0.4 mm with the spacing rule.

The bound covers how well the search finds a minimum it samples near. It does not cover a wall narrower than the sample spacing, which the check can miss. The spacing is in the result's reason, and on these parts it is 0.25 to 1.5 mm.

## Time

Measured on 2026-11-13 in `cad-analysis:5c4ce3c9a3cd` on this laptop (Apple M2, load average about 3.8 from other agents). The turned gear was read on the host.

| Part | Rays | Seconds |
| --- | --- | --- |
| arm | 31,266 | 1.46 |
| bearing_block | 35,152 | 1.00 |
| gusset | 21,398 | 0.59 |
| hex_spacer | 31,238 | 0.79 |
| l_bracket | 26,174 | 0.70 |
| motor_plate | 36,235 | 1.04 |
| plate | 39,855 | 0.99 |
| shaft_collar | 31,169 | 0.84 |
| spur_gear | 49,336 | 4.64 |
| spur_gear, turned | 49,948 | 12.39 |
| u_bracket | 33,534 | 0.99 |
| Plate 300 × 200 × 1 mm | 122,120 | 2.39 |
| Open box 250 × 200 × 100 mm, 1.5 mm walls | 124,866 | 3.90 |
| Plate 400 × 300 × 1 mm | 242,912 | 4.60 |

`min_wall` runs in the Quick lane, which gives all quick checks 60 s together. The grid has about 40,000 points or more, and the check is capped at 250,000 rays. A part with more than 10,000 faces, a search that needs more rays, or one that runs past 30 s is unknown, never a pass. The turned gear is slower because its faces' axis-aligned boxes are looser, so each ray asks more faces.

The ray count grows with the part's surface over the square of its thinnest wall, because the samples are no farther apart than that wall. A ray costs 19 to 49 µs on a part with few faces (measured in this run and the one before), so 250,000 rays take at most about 12 s, under half the 30 s cap. On such parts the ray cap, not the machine's speed, decides when the check stops. A ray costs more on a part with many faces: 94 to 250 µs on the gear. A large part with many faces can reach the 30 s cap first, and is then unknown.
