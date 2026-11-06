# Run checks

`uv run cad-sandbox run-checks <variant_id> <material_key>` runs three checks on a built variant in a second sandbox container and prints a `CheckRun` as JSON. The checks are `closed_solid`, `interference` and `mass`. The container has the limits of a build and reads only the variant's BREP, on stdin. There is no MCP tool for this yet, so a live lane drives the command after `cad-call build_variant`.

## Sub-features

- `checks-pass` returns `pass` for all three checks on the plate reference variant, each with a formula and sources, and a plate volume of 29509.72 mm^3.
- `checks-closed-solid-fail` returns `fail` for a shell with no solid and for a solid with a loose face, and names what is wrong.
- `checks-interference-fail` returns `fail` for two overlapping boxes and reports the overlap volume.
- `checks-mass` multiplies the volume by the density of the material key. The key must match a key of `tables/materials.yaml` exactly.
- `checks-unknown-key` returns `unknown` for `mass` with a key that is not in the table, and the other two checks still run.
- `checks-step` writes `result.step` beside the BREP at the first run, from the shape the checks measured.
- `checks-deterministic` prints byte-identical output for two runs of one variant.
- `checks-version` changes only the version of a check whose own file changed.
- `checks-garbage-brep` returns `fail` for `closed_solid` and `unknown` for the other two when the BREP is not a BREP, and the next run still works.
- `checks-refused` exits 1 with one line for an unknown, stale, or unbuilt variant, and starts no container.

## How to get to it (user POV)

- Run `uv run cad-sandbox run-checks <variant_id> <material_key>` in a terminal, with an id that `build_variant` returned.
- The `score_variant` tool will call the same function once it exists.

## Driving it with cad-sandbox

Preconditions:

- The preconditions of [Build variant](./build-variant.md): Docker Desktop runs and `uv run cad-sandbox build-image` exits 0.
- Material keys are `prusament-pla`, `prusament-petg`, `polymaker-polylite-abs`, `kaiser-6061-t6` and `cliffs-304`.

Set `ID` from a build, and build in the same checkout and state you check in. Any edit under `src/cad/sandbox/` or `src/cad/variants/` changes every id.

```
uv run cad-call build_variant "$(jq -Rs '{code: .}' < tests/sandbox/parts/plate.py)" > "$EVIDENCE/build-plate.json"
ID=$(jq -r .structuredContent.variant_id "$EVIDENCE/build-plate.json")
```

- **Pass.** Run `uv run cad-sandbox run-checks "$ID" prusament-pla > "$EVIDENCE/checks-plate.json"; echo $?`. Exit code `0`. `results` has `closed_solid`, `interference` and `mass`, each with `verdict` `pass`, a non-empty `formula` and a non-empty `sources` list. `mass` has a `volume` measure of 29509.72 mm^3 within 0.01 and lists the density datasheet as its last source. `step_sha256` is a hash, and `~/.cad/variants/$ID/result.step` exists.
- **Closed solid fails.** Build the plate code with `from build123d import Shell` and `result = Shell(result.faces()[:-1])` appended, then run. `closed_solid` is `fail`, its reason starts `found 0 solids` and `solids` is 0. The exit code is still `0`, because the run completed.
- **Interference fails.** Build `from build123d import *` and `result = Compound([Box(10, 10, 10), Pos(5, 5, 5) * Box(10, 10, 10)])`, then run. `interference` is `fail` with `common_volume:0-1` of 125 mm^3.
- **Mass ratio.** Run `prusament-pla` and then `kaiser-6061-t6` on one id. Both `volume` measures match, and the ratio of the two `mass` measures equals the ratio of the two densities in `tables/materials.yaml` to four digits.
- **Unknown key.** Run with `unobtainium`. `mass` is `unknown`, its reason names the key, `volume` is still measured, and the other two are `pass`. A key with a trailing space or capitals gives the same.
- **Deterministic.** Run the plate twice into two files and run `cmp` on them. Then `cmp` the `result.step` hash in both. Both pairs are identical.
- **Version.** Note each `version` in the output. Append a comment to `src/cad/checks/container/closed_solid.py`, then run again from a new process. The `closed_solid` version changed and the other two did not. Revert the edit. This re-keys no variant, because the file is outside `src/cad/sandbox/` and `src/cad/variants/`.
- **Garbage BREP.** Build a variant whose code writes a built report with random bytes as `brep` to fd 3 (`os.write(3, ...)`, then `os._exit(0)`), then run it twice. `closed_solid` is `fail` with a reason that starts `the BREP could not be read`, the other two are `unknown`, `step_sha256` is `null` and no `result.step` exists. The second run answers the same.
- **Refusals.** Run `uv run cad-sandbox run-checks fe250eb62250be75 prusament-pla; echo $?` on an id from before this change. The output is one line, `StaleVariant: variant fe250eb62250be75 was not stored by this version of the sandbox; build its code again`, and the exit code is `1`. An id that is not 16 lowercase hex digits prints an `UnknownVariant` line, and an id whose build failed prints a `NotBuilt` line. No container starts for any of them.
- **Test suite.** Run `uv run pytest tests/checks -q`. It needs Docker for the mutant, reference part, forgery and CLI tests.

## Cleanup

Each run removes its own container. After a run that was killed, list leftovers. The label marks only sandbox containers, so removing what it lists is safe.

```
docker ps -a --filter label=cad.sandbox
```

The check sources are staged in `~/.cad/stage/<16 hex digits>/`, read-only, one directory per version of `src/cad/checks/container/`. Old ones are safe to delete.

## Gotchas

- Exit code `0` means the run completed, not that the design is good. Read the three verdicts.
- `unknown` is not `pass`. A timeout, a crash, a malformed report or a missing density gives `unknown` with the cause in `reason`, and no STEP is stored.
- `result.step` appears at the first run, not at the build.
- A material key is matched exactly. There is no trimming, case folding or search.
- The table never enters a container. The host looks the density up and sends one number.
- Docker Desktop must share `~/.cad`, which it does by default. When it does not, the command prints Docker's first error line and exits `1`.
- The OCCT pages cited in each check's `sources` redirect from the 7.9.0 manual path to the current manual, so the quotes come from the 8.0.1 pages. The image runs OCP 7.9.
