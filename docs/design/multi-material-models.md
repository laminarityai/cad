# Multi-material models: several bodies in one variant

This note says how a variant comes to hold several bodies, each made of its own material, such as steel gears on a carbon fibre plate. It is stage 2 of the colour plan in [issue 285](https://github.com/laminarityai/cad/issues/285). Stage 1 colours the areas of one body and changes no check. This stage changes what several checks read, so it rests on [ADR-0014](../adr/0014-a-variant-holds-named-bodies-each-of-one-material.md), which the operator accepted on 2026-11-13. Nothing here is built yet.

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

The trial ran on trunk `493ce9a` in `cad-analysis:5c4ce3c9a3cd`, which is built from `cad-sandbox:8a7e4a0613e8` with no Python package changed. Each script called the product's own code: the build runner's `result_report` wrote the BREP, `ocp_kernel()` read it, and the real check modules and the real exporter ran on it. Each container had 2 CPUs and 2048 MB, the limits of a quick check job. The scripts are throwaway and are not in the repository.

1. **Solid order survives the BREP (measured).** For 2, 5, 12 and 24 solids, the i-th solid the check kernel reads back is the i-th solid of `result` on the build side. This held in 20 of 20 cases: distinct shapes, moved copies, mirrored shapes, a nested compound and the list form. Order follows `children`, depth first. So a solid's index is a stable key. A key of volume and centre of mass is not. It cannot tell apart a copy left in place, or a box turned 90 degrees about its own centre. Two numberings also differ on a copy left in place. build123d's `solids()` counts 1 solid there, and the kernel's explorer counts 2. The runner must number solids with the kernel's explorer, as every check does.
2. **A label lives on the Python object only (measured).** No label or colour text is in the BREP bytes. These keep a shape's `label` and `color`: `moved`, `move`, `Pos(...) *`, `translate`, `rotate`, `Rot(...) *`, the `mirror` method, `copy.copy`, `copy.deepcopy`, a `PolarLocations` pattern of copies, a cut `a - b` and an intersection `a & b`. These drop both: the `mirror`, `scale`, `fillet`, `chamfer` and `split` functions, a fuse `a + b`, and the part a `BuildPart` block makes, even with a label set inside the block. `Compound(children=[...])` keeps each child and its label. `Compound([...])` keeps the solids and drops every child, so no solid has a name. So a label must be set after the last shape operation. The simplest idiom that named every solid is to build each body, set its `label` last, and return `result = Compound(children=[plate, gears])`, where `gears` is a solid or `Compound(children=[...], label="gear")`. Each solid then takes the label of its nearest labelled node in the `children` tree. Two `BuildPart` blocks work the same way, with the label set on each block's `part` after the block. Stage 1's colour path, on branch `feat/model-colours` at `bbea554`, reads `label` and `color` from the objects the module keeps, from each node of the `children` tree and from a list named `areas`, and maps them to faces by identity (read).
3. **`interference` is not what limits the caps (measured).** The real check took 0.16 s at 24 touching boxes, 0.6 ms per pair. It took 5.0 s at 24 realistic solids, a filleted plate with 8 holes and 23 filleted gears of 20 teeth, 18 ms per pair. At 12 realistic solids it took 1.1 s. Each figure is the median of 5 warm runs. On every run over 0.1 s the spread was within 9 percent, except one 2.4 s outlier at 12 touching solids. Solids that touch cost 15 to 50 percent more per pair than solids apart. The quick job has 60 s of wall time for every quick check and the STEP (read, `WALL_SECONDS` in `src/cad/sandbox/container.py`). What limits the caps is `min_wall` once per solid. Run on each solid alone, it took 17 to 18 s for 24 boxes, 20 to 25 s for 12 realistic solids and 39 to 49 s for 24 realistic solids. Those are single runs, and the two 24-solid runs on the same shapes differ by 24 percent. closed_solid, mass and holes on each solid added at most 2.7 s. `min_wall` also has its own limit of 30 s per search (read, `MAX_SECONDS` in `min_wall.py`). Another agent shared Docker and the laptop during the runs, with a load average of 3.6 to 5.2 on 8 cores, so each figure is noisy. A hosted machine will differ.
4. **One solid taken out of the result meshes, and its faces are an offset block (measured).** Each of 4 solids (a holed plate, two filleted gears, one of them mirrored, and a spacer) was taken out with the kernel's explorer, written with `brep_bytes` and meshed by `mesh_pair` through `BrepFem.mesh`, as `fea` meshes. All 4 meshed, and on each the mesh's surfaces equal the kernel's faces, which is the rule `fea` applies before it places a load. The two gears took 13 s each for both meshes, against the stress job's 600 s. Face k of solid i is face `offset_i + k` of the whole result, where `offset_i` is the number of faces of the solids before it. This held by identity in place and by area and centroid after the BREP round trip. So a load case's faces and the stress view's highlighted faces need no map, only that offset.
5. **The exports drop every name and colour today (measured).** The product's `export` writes the STEP with `STEPControl_Writer`. It keeps the compound's tree, but each product is named "Open CASCADE STEP translator 7.9" and no colour is written. Its 3MF has one mesh object per top-level child of the BREP, here 3, with no names and no colours. Run on the labelled result before the BREP, build123d's `export_step` writes products named `plate`, `gear` and `spacer`, with the colours. The two solids of `gear` sit under a product named `gear` and read back as `COMPOUND` each, carrying the group's colour. `Mesher.add_shape` writes one named, coloured object per child of the result, here 3, and the gear body of 2 solids is one object. The export container gets only the BREP, so it has no names to write. It has to take the body list, group the solids it reads by body, set each group's label and colour, and write the STEP with XCAF. Then the STEP no longer comes from the same writer as the checks' STEP, which `export.py` names as its reason today.
6. **A hole through two stacked bodies reads as one hole on the whole result, and as two when each body is read (measured).** A 40 mm plate and a spacer, stacked on one 5.5 mm through-hole, were read by the real `holes` check. On trunk the whole result is unknown, because closed_solid fails on 2 solids. With closed_solid passing, the whole result reads 1 hole of 5.5 mm, the same as the two fused into one solid. Each solid alone reads 1 hole, so a sum over bodies counts 2, and an exact count of 1 fails. With a 6.5 mm hole in the spacer, the whole result still reads 1 hole of 5.5 mm, because the check takes coaxial faces as one hole, as it does for a counterbore. This settles the hole gap in [issue 311](https://github.com/laminarityai/cad/issues/311).

Four sentences of this design were false, and are corrected below. A solid does not carry its own label when it is built in a `BuildPart` block or a group, so the runner reads the nearest labelled node. A whole-variant hole count is not the sum of each body's holes. The exporter cannot write names from the BREP alone. The solids cap of 24 does not fit the quick job when `min_wall` reads each solid alone.

Three facts also bear on ADR-0014. The first may conflict with it, and the operator decides. The ADR says `holes` reads each body. A hole requirement on the whole variant has to read the whole result instead, or a stacked hole counts twice. The other two do not contradict it. The ADR says build code labels each solid. A label on a group of solids is the idiom that worked, and the ADR's words can be read to allow it. The ADR caps bodies at 12 and names no solids cap, so the solids cap is this design's to set.

## The design

### A body

A **body** is one or more solids of a variant's result that share a name and one material. Four gears cut from the same steel are one body named `gear` with four solids. A variant has 1 to 12 bodies and at most 12 solids. The step 0 trial set the solids cap (measured, entry 3 above). Twelve realistic solids cost about 1 s of `interference` and 20 to 25 s of `min_wall` on each solid alone, inside the quick job's 60 s. Twenty-four cost 5 s and 39 to 49 s, which leaves no room. A cap of 24 solids fits only if `min_wall` measures a moved copy once, since a moved copy shares its geometry with the original (measured), and four gears of one body are then one measurement. That is a change to `min_wall`, and step 1 may make it and raise the cap.

A variant with one unnamed solid has one body. Everything about it stays as it is today, and no stored variant changes meaning. Nothing is migrated.

### The build names its bodies

Build code returns `result` as `Compound(children=[...])`. Each solid takes the `label` of its nearest labelled node in the `children` tree: its own label, or the label of a group such as `Compound(children=gears, label="gear")` or a `BuildPart` block's `part`. Solids with the same name are one body. The runner numbers the solids with the kernel's explorer, as the checks do, and not with build123d's `solids()`, which counts a copy left in place once (measured). It reads the labels where it already reads stage 1's areas, and stores the list beside the BREP: each body's name and the indexes of the solids it covers. The solid index is the key, because the order survives the BREP and a key of volume and centre of mass does not tell every two solids apart (measured).

The agent must set a label after the last shape operation, because a fillet, a chamfer, a fuse, the `mirror` and `scale` functions and a `BuildPart` block drop it, and `Compound([...])` drops every child (measured). The tool guidance has to say so, with the idiom.

Stage 1 also reads `label`, as the name of an area of faces (read, `feat/model-colours`). So one label on a solid would name both a body and an area. Step 1 has to say which labels name bodies, for example only those on solids and groups in the `children` tree, and never those in the `areas` list (inferred).

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
| `min_wall` | Reads each body. The variant's thinnest wall is the thinnest of them, reported with its body. It is the costliest quick check on many solids: 20 to 25 s for 12 realistic solids, one at a time (measured). |
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
- **Exports.** STEP holds one named product per body, with its colour. 3MF holds one object per body, with its colour. STL has no names and no colour, and stays one mesh. Today's exporter writes no names and no colours, because it reads only the BREP (measured). It must take the body list, group the solids by body, and write the STEP through XCAF, as build123d's `export_step` does, and the 3MF with one `Mesher` object per body, which keeps both (measured).

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
1. **Bodies through the pipeline.** The stored list, `materials` on `build_variant`, the geometry checks and `mass`, the scorecard's bodies list, the explorer, and the exports.
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
- The cost of `min_wall` on a body of several solids read as one shape, and on a hosted machine. The trial timed it on each solid alone, on this laptop, with another agent using Docker.
- Whether the whole-result hole reading joins two coaxial holes of different bodies that are far apart along their axis.
- How the agent performs on a brief with several bodies. The brief set has none. Three such briefs would let the baseline measure it.
- The cost of the confirm row per body name in clicks. The design adds one row per stated name and no new page.
