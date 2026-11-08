# Checks run in an analysis image layered on the build image

Phase 3 adds a mesher, a solver and a slicer. Agent code does not need them, and every change to the image that agent code builds in changes every variant id. So there are two images.

- **Build image** (`sandbox/Dockerfile`, tag `cad-sandbox:<hash of its context>`). Agent code builds here. Its tag goes into the variant id, as before.
- **Analysis image** (`sandbox/analysis/Dockerfile`, tag `cad-analysis:<hash of its context and the build tag>`). It is built `FROM` the build image, whose tag is passed as `ARG BASE`, and adds the engines. Every check container runs here. Its tag goes into every check version, and the scorecard records the id of the image the checks ran in as `check_image_digest`. Its tag is not in the variant id.

A new analysis context changes every check version and leaves every variant id unchanged. A new build image changes both. `cad-sandbox build-image` builds both images, and the `sandbox image` step of `uv run verify` checks both.

Check containers keep every limit of build containers: no network, a read-only root, all capabilities dropped and uid 65534. A `Job` now carries its own `memory_mb` and `tmpfs_mb`, because the slow checks need more scratch space than the quick ones.

## Engines, per architecture

Each engine comes from the same Debian bookworm snapshot (`20261104T212339Z`, the date the pinned Python base image was built from), pinned by version. The same versions exist on amd64 and arm64, so a scorecard depends on the architecture only in the last bits of floating point.

| Engine | Pinned | Why not the first choice |
|---|---|---|
| gmsh | `libgmsh4.8` and `python3-gmsh` 4.8.4, with `gmsh.py` linked into Python 3.12 | The PyPI wheel (4.15.2) has no linux aarch64 build in any version, and gmsh.info ships Linux binaries for x86_64 only. conda-forge has 4.15.2 for both, but it needs a conda environment beside pip. |
| CalculiX | `calculix-ccx` 2.20 | It was the first choice. |
| Slicer | `prusa-slicer` 2.5.0 | OrcaSlicer 2.4 and 2.5 ship Linux AppImages for both architectures, built on Ubuntu 24.04. They need glibc 2.38 and GLIBCXX 3.4.32, and bookworm has glibc 2.36, so neither runs in an image built from the build image. PrusaSlicer stopped shipping Linux AppImages after 2.8, so Debian's 2.5.0 is the pinnable build. |

A test runs each engine in a check container: gmsh meshes a box, `ccx` solves a one-element deck, and `prusa-slicer --export-gcode` slices a 20 mm cube with no display and writes its estimated print time. Two slices of the cube on arm64 gave the same G-code apart from its timestamp line.

## Considered options

- **One image with everything.** Rejected. Every engine bump would change every variant id, and agent code would run next to three more engines.
- **The gmsh wheel on amd64 and Debian gmsh on arm64.** Rejected. The two architectures would mesh with different gmsh versions, so a card would differ by more than rounding.
- **Base both images on Debian trixie to keep OrcaSlicer.** Not taken here. It changes the build image, so every variant id changes again, and OCP and build123d are untested on it. On trixie arm64, OrcaSlicer 2.5.0's CLI starts with no display and no Xvfb and gets as far as validating its print settings. A full slice there needs its printer profiles and was not shown.

## Consequences

This change edits `src/cad/sandbox/`, which `TRUST_DIGEST` covers, so every variant id changes once. A stored variant is rebuilt from its signed code the next time it is scored, as the ADR-0003 amendment describes. Later changes to `sandbox/analysis/` change only check versions.

SPEC's stack table names OrcaSlicer, and the slice check is not written yet. If PrusaSlicer stays, the slice PR names its adapter `prusa.py` and renames the `orca.py` row of the engine-adapter table in `tests/checks/test_versions.py`. If the operator keeps OrcaSlicer, the trixie option above is the way to it, and it should be decided before the slice check is written. The analysis image is about 0.8 GB larger than the build image.
