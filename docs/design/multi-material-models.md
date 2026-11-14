# Multi-material models: several bodies in one variant

This note says how a variant comes to hold several bodies, each made of its own material, such as steel gears on a carbon fibre plate. It is stage 2 of the colour plan in [issue 285](https://github.com/laminarityai/cad/issues/285). Stage 1 colours the areas of one body and changes no check. This stage changes what several checks read, so it needs [ADR-0014](../adr/0014-a-variant-holds-named-bodies-each-of-one-material.md), which is proposed and not accepted. Nothing here is built.

Each fact carries one of three labels:

- **Measured** means the stage 1 prototype of 2026-11-13 produced it, in `cad-sandbox` with build123d 0.12.0.
- **Read** means it comes from the code on trunk at `ab64b29`.
- **Inferred** means neither, and the prototype in step 0 must confirm it.

## What trunk does today

- **A variant is one solid of one material.** `closed_solid` passes only when `solids = 1` (read, `src/cad/checks/container/closed_solid.py`). `mass`, `extents`, `min_wall` and `fea` require it, so a result of two solids gets no mass, no size and no stress result.
- **One material key per scored variant.** A slot's revision records one `MaterialChoice` (read, `src/cad/variant_sets/model.py:55`). A check result and a scorecard carry one `material_key` (read, `src/cad/checks/result.py:154`, `src/cad/scorecard/model.py:220`). `mass` reads one density, and `fea` reads one modulus and one strength.
- **A confirmed material pins the whole variant.** `MadeOf` holds one material key and no place for a body (read, `src/cad/briefs/model.py:122`).
- **`interference` already reads pairs of solids.** It passes when no two solids share more than 0.001 mm^3 (read, `src/cad/checks/container/interference.py`). Today it only ever sees one.
- **A supplied part is never inside `result`.** ADR-0012 keeps the person's own parts apart from the agent's body, and draws them beside it. This design leaves that as it is.

## What the stage 1 prototype measured

- A `Compound` keeps each child's `label` and `color`, and each child's faces map to faces of the result.
- A fuse and a fillet drop the label and the colour. Two solids fused are one body, which is what a person would expect.
- Face numbers on the built shape equal the face numbers in the BREP read back, for a two-child compound too.
- The 3MF writer holds one colour per object. STEP holds a colour per face through XCAF.

Not measured yet: whether the order of solids survives the BREP, how long `interference` takes on many solids, and whether the mesher can take one solid out of a compound.

## The design

### A body

A **body** is one or more solids of a variant's result that share a name and one material. Four gears cut from the same steel are one body named `gear` with four solids. A variant has 1 to 12 bodies and at most 24 solids. The caps are this design's pick, and step 0 sets them from a timing run.

A variant with one unnamed solid has one body. Everything about it stays as it is today, and no stored variant changes meaning. Nothing is migrated.

### The build names its bodies

Build code returns `result` as a compound. Each child solid carries the kernel's `label`, and solids with the same label are one body. The runner reads the labels where it already reads stage 1's areas, and stores the list beside the BREP: each body's name and the solids it covers.

The list is agent output crossing a boundary, so the server parses it into a typed, frozen, bounded record. A name is lowercase letters, digits and hyphens, up to 32 characters. This differs from stage 1 in one way. A bad colour list drops the colours and the build goes on. A bad body list refuses the build, because checks read it. The refusal names the fix, such as "two solids have no label".

A check never takes geometry from the list. It reads the solids from the BREP itself and uses the list only to learn which solid has which name.

### The agent states each body's material when it builds

`build_variant` takes a `materials` list in place of the one `material_key`. Each entry names a body, a material key and a one-line reason. The rule per body is the rule for the one material today (`src/cad/variant_sets/placement.py`):

- A confirmed `made_of` that names the body pins its key. An entry that differs is refused, and nothing is built.
- Otherwise the entry is the agent's material choice for that body, recorded with its reason and labelled agent-chosen.

The server resolves every key by exact key before it builds. After the build it compares the names in `materials` with the names the code produced. If they differ, it stores nothing and says which names are on each side.

The material is not written in build code. The kernel has no material on a shape, and an argument is typed and checked at the tool's boundary before a container starts.

### What a check reads

One job per check per variant, as today. The job's material identity becomes one of two shapes: one key, as today, or a map from body name to key. A one-body variant keeps the first shape, so its stored results and its cache keys do not change. A check reports a per-body measure under the body's name, the way `interference` already reports `common_volume:0-1`.

| Check | Change |
|---|---|
| `closed_solid` | Every solid is closed, valid and not inside out, nothing lies outside a solid, and the solids are exactly the ones the bodies name. `solids = 1` goes away. |
| `interference` | Same rule. Its message names bodies. Two bodies that touch on a face pass. A press fit drawn as an overlap fails, as it would today. |
| `mass` | `mass = sum over bodies of volume × density`, each density read by that body's exact key. It also reports `mass:<body>`. If one body's density is unknown, the total is unknown and the card asks for research on that material. A partial sum is never shown as the mass. |
| `extents` | The whole result. No change. |
| `holes` | Reads each body's holes and reports them under the body's name. |
| `min_wall` | Reads each body. The variant's thinnest wall is the thinnest of them, reported with its body. |
| `fea` | One solid at a time. See below. |
| `fit` | The whole result against each fit target. No change. |

Every changed check gets a new version, so `tests/checks/test_versions.py` and the stored results stay honest.

### Stress, one body at a time

A stress result across two bodies depends on how they are joined: bolted, glued, pressed or only touching. Nothing in the model says which. So this stage does not solve across a joint.

- A load case on a multi-body variant names one body. The check takes that body's solid out of the result and solves it alone, in that body's material. It finds the supports and the load on that body with the same geometry rules as today (ADR-0007). The person confirms the load case's words, which now name the body.
- A load case that names no body, or a body of several solids, is unknown, and the reason says to name one body of one solid.
- Every scorecard of a multi-body variant lists one more requirement under "No test yet", which reads "How the bodies are joined is not checked." It counts in coverage, so an option of several bodies never looks more checked than it is.

A solve that treats touching bodies as bonded is possible and is left for later. It needs its own reference cases, such as a two-metal beam with a known answer, and its own decision.

### A requirement can name a body

A requirement applies to the whole variant unless it names a body. `made_of`, the mass limits, `holes`, a wall limit and a load case gain an optional `body`.

The names are bound by exact key, never by matching words. When a person's brief tells bodies apart ("gray steel gears on a black carbon plate"), the proposal lists the body names, each quoting the words that state it. The person confirms the names on the card with the rest of the brief. A build for that brief must produce a body for each confirmed name, and it may add others of its own, such as a spacer. A build that lacks a confirmed name is refused, and nothing is built.

A brief that names no body works as it does today. The agent may still build several bodies and choose each material, and each choice is labelled agent-chosen.

### What the person sees

- **Scorecard.** A bodies list: each body's name, colour, material, who picked the material, its number of solids, volume and mass. A check row that reads one body names it.
- **Viewer.** Each body draws in the colour its build code set, through stage 1's path. The explorer lists the bodies under the option, and a click shows one alone.
- **Confirm card.** A row per body name the brief states, and a row per requirement as today.
- **Exports.** STEP holds one named product per body, with its colour. 3MF holds one object per body, with its colour. STL has no names and no colour, and stays one mesh.

## What the agent gains, and why checks still decide

The agent gains two choices. It chooses which solid carries which name. It chooses a body's material when the person confirmed none. Both are design choices, like its code, and neither is a verdict.

| Risk | Guard |
|---|---|
| The person confirms "the plate is carbon fibre", and the agent gives the name `plate` to a sliver. | No rule can know which solid is the plate. The card and the scorecard show each body's volume, mass and colour beside its name, and the viewer shows it alone. This risk is accepted and stated in the ADR. |
| The agent drops a body a requirement names. | The build is refused. |
| The agent splits one part into two bodies so each passes alone. | The joint line under "No test yet" is on every multi-body scorecard and counts in coverage. |
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

0. **Prototype in the sandbox, no product code.** Confirm that solid order survives the BREP, time `interference` at the caps, cut one solid from a compound for the mesher, and read names and colours back from a STEP and a 3MF.
1. **Bodies through the pipeline.** The stored list, `materials` on `build_variant`, the geometry checks and `mass`, the scorecard's bodies list, the explorer, and the exports.
2. **Requirements that name a body.** Body names on the proposal and the card, and `body` on `made_of`, the mass limits, `holes` and the wall limit.
3. **Stress on one named body.**

Each step is one PR with one live walk. The walk for step 1 is the operator's own example: gray steel gears on a black carbon fibre plate, with a mass on the scorecard that is the sum of both.

## Calls that are the operator's

1. **Accept ADR-0014.** A variant may hold several named bodies, each of one material, and the agent chooses a body's material unless the person confirmed it.
2. **Stress across joined bodies.** This design solves one named body alone and lists the joint as not checked. The other choice is to treat touching bodies as bonded and label every such verdict. That is faster to a number and can pass a part that would come apart.
3. **The word.** This design says "body", as Fusion does. Onshape says "part", which this project already uses for a context part.

## Not verified

- Everything marked inferred above, until step 0 runs.
- How the agent performs on a brief with several bodies. The brief set has none. Three such briefs would let the baseline measure it.
- The cost of the confirm row per body name in clicks. The design adds one row per stated name and no new page.
