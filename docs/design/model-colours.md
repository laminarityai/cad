# Model colours, stage 1

The operator asked for this in [issue 285](https://github.com/laminarityai/cad/issues/285): "the code generated for the 3D models should have different colors, colored logically for different parts/areas. For example, a CAD model might have gray gears and black carbon fiber." The stage 1 plan in that issue is to keep one body, let its build code colour its faces, show the colours, and carry them into the STEP. Stage 2 is a model of several bodies in different materials, and it is not approved. This note records what the prototype found and where the colours are stored.

Each fact carries one of three labels:

- **Measured** means a run on 2026-11-13 produced it, in image `cad-sandbox:8a7e4a0613e8` (build123d 0.12.0) or `cad-analysis:5c4ce3c9a3cd` (OCP, OCCT 7.9).
- **Read** means it comes from the code or the library source.
- **Inferred** means neither.

## Colour decides nothing

An area is how the model looks. No check, table read, requirement verdict or Auto step reads it. The colours come from code the agent wrote, so a check that read them would let the agent's paint decide something. `tests/test_areas_fence.py` holds two guards:

- It scans `src/cad` and fails when any module outside a short list of carriers reads `.areas` or `.areas_dropped`, looks them up with `getattr`, matches them in a `case`, dumps a whole outcome or manifest, or imports or reaches the area types. The carriers are the sandbox, the variant entry and store, the view, and the export. The scan reads names, so it is a tripwire.
- It checks that `jobs.plan` gives a variant the same checks whether its faces are coloured or grey. This is the behavioural guard: a check's job key hashes `brep_sha256`, and colour is not in the BREP.
- It fails on `outcome == Built()` outside the carriers. A coloured build is not equal to `Built()`, so that test would treat a coloured build as one that failed. The live walk found two of them: one kept every coloured build out of its set, and one would have ended an Auto run. Both now test the outcome's type.

## What the prototype answered

1. **Does the kernel keep a colour and a label through the build?** Partly (Measured).
   - They survive these steps:
     - subtracting from the shape
     - moving it with `moved()`
     - taking a BuildPart's `.part`
     - the children of a `Compound`
   - Fusing with `+` loses them, and so does `fillet`.
   - A colour set on one face from `faces()` is lost, because each call returns a new wrapper.
   - So the guidance tells the agent to fuse the model into one solid, set `color` and `label` on the final shape, and name some of its faces in `areas`. The runner still reads the children of a Compound, but a Compound of separate solids fails `closed_solid` until stage 2 allows several bodies (Measured: the walk's three-solid hook did).
   - The guidance also says colour needs no rebuild of its own. In the walk the agent built one shape 7 times, changing only its colours (Measured, same BREP hash).
   - `Compound([a, b])` keeps the faces of `a` and `b` but not their colours, and the compound has no children (Measured). The agent in the live walk wrote exactly this. So the runner also reads the colour of each shape the module keeps, such as `a` and `b`, for the faces the result still shares with it.
   - For some faces of one solid, the agent lists `Compound(faces, label=..., color=...)` in a module-level `areas` list. The runner reads that list after the shape, so a face named there takes that area's colour.
2. **Do face numbers on the built shape match the BREP the mesh reads?** Yes (Measured).
   - 12 of 12 faces match on a filleted block with a hole, and 9 of 9 on a two-child Compound.
   - `tests/sandbox/test_areas.py` checks it on every run. The faces an area lists are the faces the mesh topology finds facing up.
3. **Can the exports carry the colours with a small change?**
   - **STEP: yes (Measured).** OCCT's document writer (`STEPCAFControl_Writer`) writes a `COLOUR_RGB` for each face. It uses the same schema and the same fixed header as the plain STEP, so an export is still the same bytes each time. The colour is written in sRGB, so `#808080` is written as 0.502.
   - **STEP names: no (Measured).** OCCT 7.9 has no setting that writes a face's name, so the area names stay on the page.
   - **3MF: no (Read).** The mesher gives one colour per object, and it drops degenerate triangles, so the triangles no longer line up with the faces. A coloured 3MF needs its own triangle writer. That is not a small change, so it is left out.
   - **STL:** unchanged. The format has no colour.

## The stored shape

The runner runs inside the sandbox and reports the areas beside the BREP. The host checks that report like any other untrusted input:

```python
class Area(Frozen):
    name: AreaName  # 1 to 60 characters, no control characters
    colour: Colour  # "#rrggbb", lower case
    faces: tuple[FaceNumber, ...]  # at least one; each n >= 0


type Areas = tuple[Area, ...]  # at most 16 areas, 10,000 faces in all, no face in two


class Built(Frozen):
    kind: Literal["built"] = "built"
    areas: Areas = ()
    areas_dropped: str | None = None
```

These rules apply:

- A list that fails the check drops the colours and keeps the build. `areas_dropped` says why, in at most 200 characters, and the build tool returns it in its outcome. A runner that could not read the list at all leaves a reason too.
- `build.json` stores `Built`, so a variant's areas sit in its manifest beside the BREP hash.
- `VariantView.areas` is the copy the page reads. The view returns the areas only after the mesh is tessellated, and only when every face number they name is one of the mesh's faces. Otherwise it returns none.
- `build_variant` tells the agent each area's name, colour and `face_count`, not its face numbers, so a coloured build fits the chat's result limit. A colour lost to a fuse, a fillet or a move is missing from `areas`, and `areas_dropped` stays empty.
- An export is keyed by the BREP hash alone when there are no areas. When there are areas, the key is a hash of the BREP hash and each area's colour and faces. The STEP carries no names, so renaming an area keeps its export. If the coloured writer fails, the export writes the plain STEP. The route is `/v1/exports/{version}/{key}.{format}`.

## What a person sees

- The 3D view draws each area in its colour. A list in the corner shows each area's swatch and name.
- A model with no colours draws in neutral grey, `#a6abb0`. The old default was yellow.
- While the stress check's support and load faces show, the model draws grey, and the list dims and says why. A section draws grey the same way.
- The part to fit is drawn as a grey ghost, as before.

## What goes stale

- **Variant ids.** The id of a variant hashes the sandbox and variant code, and this change edits both. Every stored variant is now out of date (Read). Scoring an old variant rebuilds it from its stored code, and its checks run again. No check changed, so its results are new runs of the same checks, not different ones. This cannot be avoided, because the runner must report the colours.
- **Meshes and exports.** The mesh code changed (the grey default), so meshes are made again the first time each one is opened. Exports are also made again on first use.
- **Nothing is migrated.** A variant built on this code with no colour draws grey. A variant stored before it does not draw at all (Measured): its page says `OutdatedVariant: ... build its code again, or score it with score_variant to rebuild it`, and its checks say they could not be read. Every change to the sandbox or variant code since 2026-11-06 has done the same.
- **A slot keeps its old copy (Measured).** Scoring an old variant rebuilds it under a new id, but the slot still names the old id. Building the slot's same code again answers `already_member` and also leaves the old id. So the page keeps the message until the slot gets a new revision. This is older than this change.
