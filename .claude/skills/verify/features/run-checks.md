# Run checks

`uv run cad-sandbox run-checks <variant_id> <material_key>` runs five checks on a built variant in a second sandbox container and prints a `CheckRun` as JSON. The checks are `closed_solid`, `interference`, `mass`, `extents` and `holes`, the quick checks. The suite's other two, `fea` and `fit`, run only through `score_variant`, as background jobs, when a confirmed requirement or context part needs them. The container has the limits of a build and reads only the variant's BREP, on stdin. The MCP tool `score_variant` calls the same function and stores a scorecard (see [Score variant](./score-variant.md)). A live lane for the checks alone drives this command after `cad-call build_variant`.

## Sub-features

- `checks-pass` returns `pass` for all five checks on the plate reference variant, each with a formula and sources, a plate volume of 29509.72 mm^3, sorted extents of 6 x 50 x 100 mm and four round holes of 5.1 mm.
- `checks-closed-solid-fail` returns `fail` for a shell with no solid and for a solid with a loose face, and names what is wrong.
- `checks-interference-fail` returns `fail` for two overlapping boxes and reports the overlap volume.
- `checks-mass` multiplies the volume by the density of the material key. The key must match a key of `tables/materials.yaml` exactly.
- `checks-unknown-key` returns `unknown` for `mass` with a key that is not in the table, and the other checks still run.
- `checks-mass-needs-a-solid` returns `unknown` for `mass`, with no measured value, when `closed_solid` or `interference` does not pass. Its reason names that check and quotes its reason.
- `checks-extents` measures the axis-aligned bounding box of the stored BREP in mm: `extent:x`, `extent:y` and `extent:z`, and the same three as `sorted_extent:smallest`, `sorted_extent:middle` and `sorted_extent:largest`. It uses `BRepBndLib.AddOptimal_s` with no triangulation and no shape tolerance, so a 10 x 20 x 30 mm box reads exactly 10, 20 and 30. A part rotated 45 degrees about z reads wider than itself, because the box follows the axes, not the part.
- `checks-extents-needs-a-solid` returns `unknown` for `extents`, with no measured value, when `closed_solid` does not pass. A loose face or a second body would otherwise stretch the box past the part.
- `checks-holes` measures every round hole of the stored BREP: `hole_count`, `hole_diameter:0` and on, smallest first, in mm, and `unclassified_openings`. A hole is the coaxial concave cylinders whose angles add up to a full turn, so a counterbore is one hole with the narrowest diameter. The check never reads a table: the host holds the diameters to the fasteners table, or for a plain hole to its stated tolerance or a class of the tolerances table (see [Score variant](./score-variant.md)).
- `checks-holes-unknown-opening` returns `unknown` for `holes`, with the round holes still measured and `unclassified_openings` above 0, for a slot, a hexagon, an oval or a blind pocket, and never `pass`. It returns `unknown` with no measured value when `closed_solid` does not pass.
- `checks-step` writes `result.step` beside the BREP at the first run, from the shape the checks measured.
- `checks-deterministic` prints byte-identical output for two runs of one variant.
- `checks-version` changes the version of a check whose own file changed, and of each check that runs it. `mass` runs `closed_solid` and `interference`, and `extents` and `holes` run `closed_solid`, so an edit to `closed_solid.py` also changes the `mass`, `extents` and `holes` versions. An edit to any other file that scoring imports, such as `src/cad/checks/report.py`, changes all five versions.
- `checks-garbage-brep` returns `fail` for `closed_solid` and `unknown` for the other four when the BREP is not a BREP, and the next run still works.
- `checks-refused` exits 1 with one line for an unknown, stale, or unbuilt variant, and starts no container.

## How to get to it (user POV)

- Run `HOME="$CAD_HOME" uv run cad-sandbox run-checks <variant_id> <material_key>` in a terminal, with an id that `build_variant` returned.
- Call the `score_variant` tool, which runs the same function.

## Driving it with cad-sandbox

Preconditions:

- The preconditions of [Build variant](./build-variant.md): Docker Desktop runs and `uv run cad-sandbox build-image` exits 0.
- Material keys are `prusament-pla`, `prusament-petg`, `polymaker-polylite-abs`, `kaiser-6061-t6` and `cliffs-304`.

Set `ID` from a build, and build in the same checkout and state you check in. Any edit under `src/cad/sandbox/` or `src/cad/variants/` changes every id.

```
HOME="$CAD_HOME" uv run cad-call build_variant "$(jq -Rs '{code: .}' < tests/sandbox/parts/plate.py)" > "$EVIDENCE/build-plate.json"
ID=$(jq -r .structuredContent.variant_id "$EVIDENCE/build-plate.json")
```

- **Pass.** Run `HOME="$CAD_HOME" uv run cad-sandbox run-checks "$ID" prusament-pla > "$EVIDENCE/checks-plate.json"; echo $?`. Exit code `0`. `results` has `closed_solid`, `interference`, `mass`, `extents` and `holes`, each with `verdict` `pass`, a non-empty `formula` and a non-empty `sources` list. `mass` has a `volume` measure of 29509.72 mm^3 within 0.01 and lists the density datasheet as its last source. `extents` has `extent:x`, `extent:y` and `extent:z` of 100, 50 and 6 mm within 0.002 (the plate lies flat with its long side on x) and sorted extents of 6, 50 and 100 mm. `holes` has `hole_count` 4 and four `hole_diameter:i` of 5.1 mm within 0.001, and `unclassified_openings` 0. `step` is `{"kind": "stored", "sha256": <hash>}`, and `$CAD_HOME/.cad/variants/$ID/result.step` exists.
- **Closed solid fails.** Build the plate code with `from build123d import Shell` and `result = Shell(result.faces()[:-1])` appended, then run. `closed_solid` is `fail`, its reason starts `found 0 solids` and `solids` is 0. `mass`, `extents` and `holes` are `unknown` with an empty `measured` list, and their reasons start `closed_solid is fail`. The exit code is still `0`, because the run completed.
- **Interference fails.** Build `from build123d import *` and `result = Compound([Box(10, 10, 10), Pos(5, 5, 5) * Box(10, 10, 10)])`, then run. `interference` is `fail` with `common_volume:0-1` of 125 mm^3. `mass` is `unknown` with an empty `measured` list, because `closed_solid` fails on 2 solids.
- **Mass ratio.** Run `prusament-pla` and then `kaiser-6061-t6` on one id. Both `volume` measures match, and the ratio of the two `mass` measures equals the ratio of the two densities in `tables/materials.yaml` to four digits.
- **Unknown key.** Run with `unobtainium`. `mass` is `unknown`, its reason names the key, `volume` is still measured, and the other four are `pass`. A key with a trailing space or capitals gives the same.
- **Deterministic.** Run the plate twice into two files and run `cmp` on them. Then `cmp` the `result.step` hash in both. Both pairs are identical.
- **Version.** Note each `version` in the output. Append a comment to `src/cad/checks/container/closed_solid.py`, then run again from a new process. The `closed_solid`, `mass`, `extents` and `holes` versions changed and the `interference` version did not. Revert the edit. This re-keys no variant, because the file is outside `src/cad/sandbox/` and `src/cad/variants/`.
- **Garbage BREP.** Build a variant whose code writes a built report with random bytes as `brep` to fd 3 (`os.write(3, ...)`, then `os._exit(0)`), then run it twice. `closed_solid` is `fail` with a reason that starts `the BREP could not be read`, the other four are `unknown`, `step` is `{"kind": "missing"}` with a `reason` that says the BREP could not be read, and no `result.step` exists. The second run answers the same.
- **Refusals.** Run `HOME="$CAD_HOME" uv run cad-sandbox run-checks fe250eb62250be75 prusament-pla; echo $?` on an id from before this change. The output is one line, `StaleVariant: variant fe250eb62250be75 was not stored by this version of the sandbox; build its code again`, and the exit code is `1`. An id that is not 16 lowercase hex digits prints an `UnknownVariant` line, and an id whose build failed prints a `NotBuilt` line. No container starts for any of them.
- **Test suite.** Run `uv run pytest tests/checks -q`. It needs Docker for the mutant, reference part, forgery and CLI tests.

## Cleanup

Each run removes its own container. After a run that was killed, list leftovers. The label marks only sandbox containers, so removing what it lists is safe.

```
docker ps -a --filter label=cad.sandbox
```

The check sources are staged in `$CAD_HOME/.cad/stage/<16 hex digits>/`, read-only, one directory per version of the files `cad.checks.container.runner` imports, package `__init__.py` files included. Old ones are safe to delete.

## Gotchas

- Exit code `0` means the run completed, not that the design is good. Read the five verdicts.
- `unknown` is not `pass`. A timeout, a crash, a malformed report or a missing density gives `unknown` with the cause in `reason`, and no STEP is stored.
- `result.step` appears at the first run, not at the build.
- A material key is matched exactly. There is no trimming, case folding or search.
- The table never enters a container. The host looks the density up and sends one number.
- Docker Desktop must share `~/.cad`, which it does by default. When it does not, the command prints Docker's first error line and exits `1`.
- The OCCT pages cited in each check's `sources` redirect from the 7.9.0 manual path to the current manual, so the quotes come from the 8.0.1 pages. The image runs OCP 7.9.
