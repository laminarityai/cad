# Multi-material models: several bodies in one variant

This note says how a variant comes to hold several bodies, each made of its own material, such as steel gears on a carbon fibre plate. It is stage 2 of the colour plan in [issue 285](https://github.com/laminarityai/cad/issues/285). Stage 1 colours the areas of one body and changes no check. This stage changes what several checks read, so it rests on [ADR-0014](../adr/0014-a-variant-holds-named-bodies-each-of-one-material.md), which the operator accepted on 2026-11-13. Step 1 of the build order is built in two pull requests, and "What step 1 settled" below says what it chose and measured. Steps 2 and 3 are not built.

Each fact carries one of three labels:

- **Measured** means the stage 1 prototype or the step 0 trial of 2026-11-13 produced it, in the sandbox images with build123d 0.12.0 and OCP 7.9.3.1.1.
- **Read** means it comes from the code on trunk at `ab64b29`, or at `493ce9a` for the step 0 trial.
- **Inferred** means none of these.

## What trunk does today

- **A variant is one solid of one material.** `closed_solid` passes only when `solids = 1` (read, `src/cad/checks/container/closed_solid.py`). `mass`, `extents`, `holes`, `min_wall` and `fea` each list it in `REQUIRES` (read), so a result of two solids gets no mass, no size, no hole reading, no wall reading and no stress result.
- **One material key per scored variant.** A slot's revision records one `MaterialChoice` (read, `src/cad/variant_sets/model.py:95`). A check run and a scorecard carry one `material_key` (read, `src/cad/checks/result.py:154`, `src/cad/scorecard/model.py:220`). `mass` reads one density, and `fea` reads one modulus and one strength.
- **A confirmed material pins the whole variant.** `MadeOf` holds one material key and no place for a body (read, `src/cad/briefs/model.py:122`).
- **`interference` already reads pairs of solids.** It passes when no two solids share more than 0.001 mm^3 (read, `src/cad/checks/container/interference.py`). It requires no other check, so it already runs on a result of two solids today, while `closed_solid` fails that result.
- **A supplied part is never inside `result`.** ADR-0012 keeps the person's own parts apart from the agent's body, and draws them beside it. This design leaves that as it is.

## What the stage 1 prototype measured

- A `Compound` keeps each child's `label` and `color`, and each child's faces map to faces of the result.
- A fuse and a fillet drop the label and the colour. Two solids fused are one body, which is what a person would expect.
- Face numbers on the built shape equal the face numbers in the BREP read back, for a two-child compound too.
- The 3MF writer holds one colour per object. STEP holds a colour per face through XCAF.

## What the step 0 trial measured

The trial ran on trunk `493ce9a` in `cad-analysis:5c4ce3c9a3cd`, which is built from `cad-sandbox:8a7e4a0613e8` with no Python package changed. Each script called the product's own code: the build runner's `result_report` wrote the BREP, `ocp_kernel()` read it, and the real check modules and the real exporter ran on it. The rule that names each solid by its nearest labelled node is the trial's own, in `common.py`, because the product has none yet. Each container had 2 CPUs and 2048 MB, the limits of a quick check job. The scripts are throwaway and are not in the repository. An independent review reran four scripts of its own in the same image under the same limits, and its figures are marked as the review rerun.

1. **Solid order survives the BREP (measured).** For 2, 5, 12 and 24 solids, the i-th solid the check kernel reads back is the i-th solid of `result` on the build side. This held in 20 of 20 cases: distinct shapes, moved copies, mirrored shapes, a nested compound and the list form. Order follows `children`, depth first. So a solid's index is a stable key. A key of volume and centre of mass is not. It cannot tell apart a copy left in place, or a square box turned 90 degrees about its own centre, which fills the same space. Two numberings also differ on a copy left in place. build123d's `solids()` counts 1 solid there, and the kernel's explorer counts 2. The runner must number solids with the kernel's explorer, as every check does.
2. **A label lives on the Python object only (measured).** No label or colour text is in the BREP bytes. These keep a shape's `label` and `color`: `moved`, `move`, `Pos(...) *`, `translate`, `rotate`, `Rot(...) *`, the `mirror` method, `copy.copy`, `copy.deepcopy`, a `PolarLocations` pattern of copies, a cut `a - b` and an intersection `a & b`. These drop both: the `mirror`, `scale`, `fillet`, `chamfer` and `split` functions, a fuse `a + b`, and the part a `BuildPart` block makes, even with a label set inside the block. `Compound(children=[...])` keeps each child and its label. `Compound([...])` keeps the solids and drops every child, so no solid has a name. So a label must be set after the last shape operation. The simplest idiom that named every solid is to build each body, set its `label` last, and return `result = Compound(children=[plate, gears])`, where `gears` is a solid or `Compound(children=[...], label="gear")`. Each solid then takes the label of its nearest labelled node in the `children` tree. Two `BuildPart` blocks work the same way, with the label set on each block's `part` after the block. Stage 1's colour path, on branch `feat/model-colours` at `bbea554`, reads `label` and `color` from the objects the module keeps, from each node of the `children` tree and from a list named `areas`, and maps them to faces by identity (read).
3. **`interference` is not what limits the caps (measured).** The real check took 0.16 s at 24 touching boxes, 0.6 ms per pair. It took 5.0 s at 24 realistic solids, a filleted plate with 8 holes and 23 filleted gears of 20 teeth, 18 ms per pair. At 12 realistic solids it took 1.1 s. Each figure is the median of 5 warm runs. On every row over 0.1 s, each run was within 7 percent of the row's median, except one 2.4 s run at 12 realistic touching solids. On those rows, solids that touch cost 16 to 49 percent more per pair than solids apart. The quick job has 60 s of wall time for every quick check and the STEP (read, `WALL_SECONDS` in `src/cad/sandbox/container.py`). `min_wall` costs about the same per call, because it spreads one grid of at most 40000 points over every face it is given (read, `GRID_POINTS` in `min_wall.py`). So its cost grows with the number of calls, not the number of solids. Run on each solid alone, it took 17 to 18 s for 24 boxes, 20 to 25 s for 12 realistic solids and 39 to 49 s for 24 realistic solids. Those are single runs, and the two 24-solid runs on the same shapes differ by 24 percent. Read once per body, the 23 gears of the 24-solid result took 6.4 s as one shape and found the same thinnest wall, and twelve bodies of 2 solids each took 23.5 s in all (measured, review rerun). A body read as one shape gets a coarser grid, and the miss recorded below came of it (measured). So the check now reads each solid alone, as the `min_wall` row below says. closed_solid, mass and holes on each solid added at most 2.7 s. `min_wall` also has its own limit of 30 s, which every solid of a variant shares (read, `MAX_SECONDS` in `min_wall.py`). Another agent shared Docker and the laptop during the runs, with a load average of 3.6 to 5.2 on 8 cores, so each figure is noisy. A hosted machine will differ.
4. **One solid taken out of the result meshes, and its faces are an offset block (measured).** Each of 4 solids (a holed plate, two filleted gears, one of them mirrored, and a spacer) was taken out with the kernel's explorer, written with `brep_bytes` and meshed by `mesh_pair` through `BrepFem.mesh`, as `fea` meshes. All 4 meshed, and on each the mesh's surfaces equal the kernel's faces, which is the rule `fea` applies before it places a load. The two gears took 13 s each for both meshes, against the stress job's 600 s. Face k of solid i is face `offset_i + k` of the whole result, where `offset_i` is the number of faces of the solids before it. This held by identity in place and by area and centroid after the BREP round trip. So a load case's faces and the stress view's highlighted faces need no map, only that offset.
5. **The exports drop every name and colour today (measured).** The product's `export` writes the STEP with `STEPControl_Writer`. It keeps the compound's tree, but each product is named "Open CASCADE STEP translator 7.9" and no colour is written. `Mesher.read` finds 3 shapes in its 3MF, one per top-level child of the BREP, with no names and no colours. Run on the labelled result before the BREP, build123d's `export_step` writes products named `plate`, `gear` and `spacer`, with the colours. The two solids of `gear` sit under a product named `gear` and read back as `COMPOUND` each, carrying the group's colour. `Mesher.add_shape` writes one named, coloured object per child of the result, here 3, and the gear body of 2 solids is one object. The export container gets only the BREP, so it has no names to write. It has to take the body list, group the solids it reads by body, set each group's label and colour, and write the STEP with XCAF. Then the STEP no longer comes from the same writer as the checks' STEP, which `export.py` names as its reason today.
6. **A hole through two stacked bodies reads as one hole on the whole result, and as two when each body is read (measured).** A 40 mm plate and a spacer, stacked on one 5.5 mm through-hole, were read by the real `holes` check. On trunk the whole result is unknown, because closed_solid fails on 2 solids. With closed_solid's verdict forced to pass in the script, since no code passes it on two solids today, the whole result reads 1 hole of 5.5 mm, the same as the two fused into one solid. `holes` reads only that verdict, so forcing it does not change what `holes` measures (read, `required_pass` in `check.py`). Each solid alone reads 1 hole, so a sum over bodies counts 2, and an exact count of 1 fails. With a 6.5 mm hole in the spacer, the whole result still reads 1 hole of 5.5 mm, because the check takes coaxial faces as one hole, as it does for a counterbore. The whole result also reads two coaxial holes of two bodies 50 mm apart as 1 hole, because the check groups holes by axis line alone, as it does in one solid today (read, `_hole_groups` in `features.py`; measured, review rerun). So reading the whole result counts holes the way one fused solid does. It narrows the hole gap in [issue 311](https://github.com/laminarityai/cad/issues/311) and does not close it.

One sentence of this design was false, and is corrected below. A solid does not carry its own label when it is built in a `BuildPart` block or a group, so the runner reads the nearest labelled node. The trial also filled two gaps. A whole-variant hole count must not be the sum of each body's holes, and the exporter cannot write names from the BREP alone.

Three facts also bear on ADR-0014. The operator decided the first on 2026-11-13, and the ADR's amendment of that date records it. The ADR first said `holes` reads each body. A hole requirement on the whole variant has to read the whole result instead, or a stacked hole counts twice. Read that way, two separate holes of two bodies on one axis count once, as they do in one solid today. The other two do not contradict it. The ADR says build code labels each solid. A label on a group of solids is the idiom that worked, and the ADR's words can be read to allow it. The ADR caps bodies at 12 and names no solids cap, so the solids cap is this design's to set.

## The design

### A body

A **body** is one or more solids of a variant's result that share a name and one material. Four gears cut from the same steel are one body named `gear` with four solids. A variant has 1 to 12 bodies and at most 24 solids. The caps are this design's pick. At 24 realistic solids in 12 bodies of 2, `interference` took about 5 s (measured, entry 3 above). `min_wall` reads each solid alone and stops at its own 30 s, so the quick job stays inside its 60 s: at 24 solids of about 100 faces it took 36.3 to 37.0 s (measured, fix round). The cap no longer fits `min_wall`. A body of 12 to 14 such solids already needs more than its 30 s on this laptop, and from there it reads unknown (measured, fix round). The cap is left as it is, and the change is a decision for the operator.

A variant with one unnamed solid has one body. Everything about it stays as it is today, and no stored variant changes meaning. Nothing is migrated.

### The build names its bodies

Build code returns `result` as `Compound(children=[...])`. Each solid takes the `label` of its nearest labelled node in the `children` tree: its own label, or the label of a group such as `Compound(children=gears, label="gear")` or a `BuildPart` block's `part`. Solids with the same name are one body. The runner numbers the solids with the kernel's explorer, as the checks do, and not with build123d's `solids()`, which counts a copy left in place once (measured). It reads the labels where it already reads stage 1's areas, and stores the list beside the BREP: each body's name and the indexes of the solids it covers. The solid index is the key, because the order survives the BREP and a key of volume and centre of mass does not tell every two solids apart (measured).

The agent must set a label after the last shape operation, because a fillet, a chamfer, a fuse, the `mirror` and `scale` functions and a `BuildPart` block drop it, and `Compound([...])` drops every child (measured). The tool guidance has to say so, with the idiom.

Stage 1 also reads `label`, as the name of an area of faces. So one label on a solid names both a body and an area, and step 1 says which labels name bodies. See the label rule under "What step 1 settled".

The list is agent output crossing a boundary, so the server parses it into a typed, frozen, bounded record. A name starts with a lowercase letter and holds lowercase letters, digits and hyphens, up to 32 characters, so it never reads as a solid index. This differs from stage 1 in one way. A bad colour list drops the colours and the build goes on. A bad body list refuses the build, because checks read it. The refusal names the fix, such as "two solids have no label".

A check never takes geometry from the list. It reads the solids from the BREP itself and uses the list only to learn which solid has which name.

### The agent states each body's material when it builds

`build_variant` takes a `materials` list in place of the one `material_key`. Each entry names a body, a material key and a one-line reason. The rule per body is the rule for the one material today (`src/cad/variant_sets/placement.py`):

- A confirmed `made_of` that names the body pins its key, and one that names no body pins every body's key. An entry that differs is refused, and nothing is built.
- Otherwise the entry is the agent's material choice for that body, recorded with its reason and labelled agent-chosen.

The server resolves every key by exact key before it builds. After the build it compares the names in `materials` with the names the code produced. If they differ, it stores nothing and says which names are on each side.

The material is not written in build code. The kernel has no material on a shape, and an argument is typed and checked at the tool's boundary before a container starts.

`score_variant`, the scorecard read and `auto_start` take the same `materials` list wherever they take `material_key` today. A single `material_key` on a variant of more than one body is refused.

### What a check reads

The jobs stay as today: one quick job for the quick checks, one `fea` job per load case and one `fit` job per context part (read, `src/cad/checks/jobs.py`). The job's material identity becomes one of two shapes: one key, as today, or a map from body name to key. A variant of one unnamed solid keeps the first shape, so its stored results keep their meaning. Every job key still changes once, because each check's version hashes the container's source (read, `src/cad/checks/report.py`). The body list goes to the container in the request wire, so it is part of every job key, and two builds with the same BREP and different names never share a result. A check reports a per-body measure as the measure's name, a colon and the body's name, such as `mass:plate`.

| Check | Change |
|---|---|
| `closed_solid` | Every solid is closed, valid and not inside out, nothing lies outside a solid, and the solids are exactly the ones the bodies name. `solids = 1` goes away. |
| `interference` | Same rule, over every pair of solids, two solids of one body included. Its message names each solid's body. Pair measures stay keyed by solid index, as `common_volume:0-1`. Its `bodies` measure counts solids, so it is renamed `solids`. Two bodies that touch on a face pass. A press fit drawn as an overlap fails, as it would today. |
| `mass` | `mass = sum over bodies of volume × density`, each density read by that body's exact key. It also reports `mass:<body>`. If one body's density is unknown, the total is unknown and the card asks for research on that material. A partial sum is never shown as the mass. |
| `extents` | The whole result. No change. |
| `holes` | A requirement on the whole variant reads the whole result, so a hole through two stacked bodies counts once, as it does when they are fused (measured). A requirement that names a body reads that body's solids. A sum over bodies would count the stacked hole twice and fail an exact count (measured). |
| `min_wall` | Reads each solid of each body alone, on a grid of its own, so no solid is sampled more coarsely than it would be alone. A body's wall is the thinnest of its solids, and the variant's is the thinnest of its bodies, reported with its body. Every solid shares one 30 s limit, and past it the check reads unknown. With a block and gears of about 100 faces, 13 solids passed in a 31.7 s quick job and 14 read unknown in one run, and 12 read unknown in a later run with more load (measured, fix round). |
| `fea` | One solid at a time. See below. |
| `fit` | The whole result against each fit target. No change. |

Every changed check gets a new version, so `tests/checks/test_versions.py` and the stored results stay honest.

An approved agent-written check (ADR-0011) reads one material today (read, `src/cad/operations/agent_checks.py:110`). On a variant of more than one body its verdict is unknown, and its reason says the check reads one material.

### Stress, one body at a time

A stress result across two bodies depends on how they are joined: bolted, glued, pressed or only touching. Nothing in the model says which. So this stage does not solve across a joint.

- A load case on a variant of more than one solid names one body. The check takes that body's solid out of the result and solves it alone, in that body's material. The lone solid meshes on the same path, and its face k is face `offset + k` of the whole result, where the offset counts the faces of the solids before it (measured). So the load's faces and the stress view's faces convert by that offset alone. It finds the supports and the load on that body with the same geometry rules as today (ADR-0007). The person confirms the load case's words, which now name the body.
- A load case that names no body, or a body of several solids, is unknown, and the reason says to name one body of one solid.
- Every scorecard of a variant of more than one solid lists one more requirement under "No test yet", which reads "How the bodies are joined is not checked." It counts in coverage, so an option of several bodies never looks more checked than it is.

A solve that treats touching bodies as bonded is possible and is left for later. It needs its own reference cases, such as a two-metal beam with a known answer, and its own decision.

### A requirement can name a body

A requirement applies to the whole variant unless it names a body. `made_of`, the mass limits, the two hole requirements, a limit on a per-body measure such as the thinnest wall, and a load case gain an optional `body`.

The names are bound by exact key, never by matching words. When a person's brief tells bodies apart ("gray steel gears on a black carbon plate"), the proposal lists the body names, each quoting the words that state it. The person confirms the names on the card with the rest of the brief. A build for that brief must produce a body for each confirmed name, and it may add others of its own, such as a spacer. A build that lacks a confirmed name is refused, and nothing is built. A variant built before the names were confirmed may lack one. A requirement that names a body the variant lacks is unknown, and its reason names the body.

A brief that names no body works as it does today. The agent may still build several bodies and choose each material, and each choice is labelled agent-chosen.

### What the person sees

- **Scorecard.** A bodies list: each body's name, colour, material, who picked the material, its number of solids, volume and mass. A check row that reads one body names it.
- **Viewer.** Each body draws in the colour its build code set, through stage 1's path. The explorer lists the bodies under the option, and a click shows one alone.
- **Confirm card.** A row per body name the brief states, and a row per requirement as today.
- **Exports.** STEP holds one named product per body, with its colour. 3MF holds one object per body, with its colour. STL has no names and no colour, and stays one mesh. The exporter reads only the BREP, which carries no names (measured), so the export job takes the body list as well. A variant of one unnamed body is written as before.

## What step 1 settled

Each of these is built, with tests in the folders the change touches.

- **The label rule.** A `result` of one solid, or none, is one unnamed body whatever its label says, so every stored variant keeps its meaning. With two or more solids, each solid takes the `label` of its nearest labelled node in the `children` tree, read where stage 1 reads its areas. A label in the `areas` list never names a body. Solids that share a name are one body. An unlabelled solid, a name that breaks the name rule, more than 12 bodies or more than 24 solids refuses the build, and the refusal names the fix (read, `src/cad/sandbox/runner.py` `bodies`, `src/cad/sandbox/bodies.py` `read_bodies`). So a stored variant of two or more solids with no label, which failed `closed_solid` before, is refused when the server rebuilds it to score it, and the refusal names the fix (read, `src/cad/scorecard/score.py` `open_or_rebuild`). A node of the `children` tree names its area by the same rule, because a child takes its parent's colour but not its label: before this, a colour on a labelled Compound of two gears made an area named `unnamed` (measured, the walk's gear plate; `tests/sandbox/test_build_bodies.py`). A body's colour on the scorecard is the colour of the area of its name, and a body whose code coloured none of its solids shows no swatch.
- **`materials`, at the fewest calls (issue 311).** `build_variant`, `score_variant`, the scorecard read and `auto_start` take `materials`, a list of `{body, key}` with a one-line `reason` where a choice is recorded. Every key resolves by exact key before any container starts. An entry left out keeps the material the slot recorded for that body's name, so a revision that changes one body's shape needs no `materials` at all, and one that changes one body's material sends one entry. A confirmed `made_of` pins every body, so the agent passes nothing, and an entry that differs is refused. The names are compared after the build, because only the build knows them. If they differ, the refusal names both sides and says the variant is stored and joined to no slot, so the next call can name the bodies and needs no rebuild. One `material_key` on a variant of more than one body is refused, and `materials` and `material_key` together are refused (read, `src/cad/variant_sets/placement.py` `choose_each`, `src/cad/scorecard/material.py` `made_of`).
- **The binding.** The body list and each body's values go to the container in the request wire, so they are in every job key. Two builds with the same BREP and different names never share a result. The list's hash is in the signed manifest and on each `CheckRun` and scorecard. The largest request a variant can send, 12 bodies of 32-character names with 24 solids and every quick check, is 31676 bytes with 64-character material keys the table lacks, and 5238 bytes with the table's longest keys. One container argument may hold 128 KiB on Linux, and a test keeps the request under half of it (measured, `tests/checks/test_body_request.py`).
- **The joint line.** A scorecard of more than one body carries `untested`, which holds "How the bodies are joined is not checked." The page lists it under "No test yet". The brief-set tracker counts it as one requirement with no check, once per scored card that has a brief, so the coverage of an option of several bodies falls (read, `evals/briefs/tracking.py`).
- **`holes`** reads the whole result, as the ADR's amendment of 2026-11-13 says. Two 40 x 40 x 5 mm plates 50 mm apart, each with a 6 mm hole on one axis, read 1 hole of 6 mm (measured, `tests/scorecard/test_bodies.py`).
- **`min_wall` missed a point-like wall in a body of many solids, and now reads each solid alone (measured).** A 20 x 20 x 10 mm block was read with three thin walls: a 0.6 mm web beside an 8 mm hole, a 0.4 mm web beside a 1 mm hole, and a 0.3 mm wall at the one point where two 1 mm holes cross at right angles. It was read alone, then as one solid of a body with 11 gears, then with 23 gears. Each gear had 20 square teeth and about 100 faces. The sample spacing grew from 0.2 mm alone to 0.85 mm with 12 solids and 1.25 mm with 24. Both webs along a hole were found at 0.6 and 0.4 mm at every size. **The crossed holes' 0.3 mm wall was found alone and missed in both bodies.** The check passed with 2 mm, the gear teeth, so a requirement of at least 1 mm would pass a part with 0.3 mm. The same faces fused into one solid ran past the 30 s limit and read unknown, so this trial cannot say whether one solid of that many faces misses it too. The whole quick job took 1.7 s alone, 4.9 s at 12 solids and 9.0 to 9.2 s at 24 solids in one body, against its 60 s. The fix round gave each solid a grid of its own under the one 30 s limit, and kept `GRID_POINTS` and `MAX_SECONDS`. A unit test reproduces the miss on the old reading: the crossed holes with a 300 x 300 x 5 mm plate in the same body read 4.5 mm at 2.19 mm spacing, and read 0.3 mm now (`tests/checks/test_min_wall_walls.py`). The fix round reran the trial in the sandbox, on a block with only the crossed holes and gears of 20 square teeth and about 100 faces. The table gives the whole quick job's seconds, with a load average of 4.7 to 6.1 on 8 cores.

  | Solids in the body | 0.3 mm wall | Spacing | Quick job | `min_wall` |
  | --- | --- | --- | --- | --- |
  | 1 | found | 0.208 mm | 2.1 s | pass |
  | 12 | not read | none | 32.8 s | unknown, past 30 s |
  | 24 | not read | none | 36.3 s | unknown, past 30 s |

  An earlier run of the same reading, with gears that differ in hub radius, passed 12 solids in 31.0 s and 13 in 31.7 s, each at 0.208 mm, and read 14 unknown (measured). So the count where it turns unknown sits at 12 to 14 on this laptop and moves with load. On the old reading, those gears gave 0.731 mm spacing at 12 solids and 1.06 mm at 24 and found the wall by the luck of the grid (measured). They did not reproduce the step 1 miss, so the 0.85 and 1.25 mm figures above are step 1's.
- **The explorer, one body alone, and the exports by body.** The mesh is one part of every face and has no solid map, so the tessellation reports how many faces each solid has, and the view turns that into each body's face numbers. The count of each solid's faces, read solid by solid, adds up to the whole shape's faces, because `Shape.solids()` followed by each solid's `faces()` gives the whole shape's `faces()` in order (measured, the gear plate: 6, 3 and 3 faces, 12 in all). A copy left in place makes build123d count one solid where the kernel's explorer counts two, so the counts do not add up and the variant has no body faces: it shows whole and its export has no names. The explorer lists each body under its option with its material. A click shows the body alone: the other faces and the edges that border none of the body's faces are drawn with a count of nothing, so every index stays the same and a click still names the same face. A second click on it brings the whole model back. The export job takes the body list, and its key is the BREP's hash while there are no bodies, so a variant of one body keeps its export. The STEP is an XCAF assembly: a product `result` over one product per body, each named as its body is, with each area's faces coloured on the body that holds them. The 3MF is one labelled, coloured compound per body, so it holds one named object per body. If the coloured writer fails or the bodies do not match the shape, the plain STEP and the plain 3MF are written, because names and colours are how the model looks and losing them must not lose the file. The 2026-11-13 walk built the gear plate (steel gears on a carbon fibre plate) in a throwaway home with no model call. The explorer listed `plate` and `gear` with their materials, a click on `gear` drew the two cylinders alone, and a second click brought the plate back. The STEP held the products `result`, `plate` and `gear` with 3 solids and the colours black and gray, and the 3MF held the objects `plate` and `gear` (measured; screenshots in `docs/review/bodies/`). A block of one body downloaded a STEP whose hash was the scorecard's, as on trunk (measured). Nothing a check reads comes from any of this (read, `src/cad/geometry/bodies.py`, `src/cad/geometry/container/coloured_step.py`, `src/cad/geometry/container/named_bodies.py`; `tests/geometry/test_export_bodies.py`).
- **Left for later PRs.** `body` on a requirement and body names on the proposal and the Confirm card are step 2. Stress on one named body is step 3.

## What the agent gains, and why checks still decide

The agent gains two choices. It chooses which solid carries which name. It chooses a body's material when the person confirmed none. Both are design choices, like its code, and neither is a verdict.

| Risk | Guard |
|---|---|
| The person confirms "the plate is carbon fibre", and the agent gives the name `plate` to a sliver. | No rule can know which solid is the plate. The card and the scorecard show each body's volume, mass and colour beside its name, and the viewer shows it alone. This risk is accepted and stated in the ADR. |
| The agent drops a body a requirement names. | The build is refused. |
| The agent splits one part into two solids, in one body or two, so each passes alone. | The joint line under "No test yet" is on every scorecard of more than one solid and counts in coverage. |
| The agent gives a load case's body name to the stiffest solid. | The same guard as the sliver, and the same accepted risk. The supports and the load inside the body still come from ADR-0007's fixed rules. |
| A colour or a name reaches a verdict. | Stage 1's test, that no check and no table reads a colour, stays. A name only selects solids that the check then measures itself. |
| A material value is forged. | No change. Every value comes from the tables by exact key, or from research under ADR-0009. |

## What stays out

- Stress across a joint, and any model of bolts, glue or press fits.
- Motion. No check knows that two gears mesh.
- The mass of supplied parts. ADR-0012 already lists total mass with supplied parts as later work.
- Rules for printing in several materials. Printability is deferred.
- A colour per material from a table. The colour is the agent's choice, as in stage 1.

## Build order

Stage 2 starts after stage 1 merges, because it extends the list stage 1 stores beside the BREP.

0. **Prototype in the sandbox, no product code.** Done on 2026-11-13. See "What the step 0 trial measured".
1. **Bodies through the pipeline (built).** The stored list, `materials` on `build_variant`, the geometry checks and `mass`, the scorecard's bodies list, the explorer, and the exports.
2. **Requirements that name a body.** Body names on the proposal and the card, and `body` on `made_of`, the mass limits, the hole requirements and a limit on a per-body measure.
3. **Stress on one named body.**

The independent review of this design left gaps for the builder, sorted by step in [issue 311](https://github.com/laminarityai/cad/issues/311). One of them is SPEC.md's line on the universal checks, which still says "one closed solid". It changes with step 1 and needs the operator's word.

Each step is one PR with one live walk. The walk for step 1 is the operator's own example: gray steel gears on a black carbon fibre plate, with a mass on the scorecard that is the sum of both.

## The operator's calls

The operator made all three on 2026-11-13.

1. **ADR-0014 is accepted.** A variant may hold several named bodies, each of one material, and the agent chooses a body's material unless the person confirmed it.
2. **The stress check solves one named body alone.** The joint is listed as not checked. A solve that treats touching bodies as bonded stays out.
3. **The word is "body".**

## Not verified

- Everything marked inferred above.
- The cost of `min_wall` on a hosted machine. The trial, the review rerun and the fix round timed it on this laptop, with other work using Docker, so the count of solids at which it reads unknown will differ there.
- A whole quick job at 24 solids in 12 bodies, end to end. Step 1 timed 24 solids in one body at 9.0 to 9.2 s, and 12 bodies were timed only as sums of single checks.
- How the agent performs on a brief with several bodies. The brief set has none. Three such briefs would let the baseline measure it.
- The cost of the confirm row per body name in clicks. The design adds one row per stated name and no new page.
