# Geometry

`geometry(variant_id)` is a person-only operation in `src/cad/operations/geometry.py`. It returns the variant's mesh in three-cad-viewer's shapes format. The analysis image tessellates the BREP that the checks measured, in the background, once per BREP. The mesh is stored under `$CAD_HOME/.cad/geometry/<version>/<brep_sha256>.json`, where the version names the analysis image and the tessellator sources. It has no MCP tool, because an agent has no use for a mesh, and its HTTP route is `GET /v1/variants/{variant_id}/geometry`, which the web shell's viewer reads.

## Sub-features

- `mesh-volume` encloses the volume the `mass` check measured, within 0.5%, for each bake-off part.
- `mesh-renders` renders in three-cad-viewer.
- `pending` returns `pending` while the job runs, and starts no second job for the same BREP.
- `stored` reads a stored mesh, or a stored failure for a BREP the kernel cannot read, with no job. A timeout is not stored, so the next read runs the job again.
- `not-a-tool` is missing from the MCP tool list, because its audience is `PERSON`.

## How to get to it (user POV)

The workspace page's viewer reads it at `GET /v1/variants/{variant_id}/geometry`, next to the scorecard. [Download](./download.md) is the file a person takes away.

## Driving it with geometry.py

Preconditions: those of [Score variant](./score-variant.md).

```
uv run python .claude/skills/verify/scripts/geometry.py "$EVIDENCE/geometry" tests/sandbox/parts/plate.py tests/sandbox/parts/spur_gear.py
```

For each part, the script builds and scores it through the MCP server on stdio, with `HOME` set to `$EVIDENCE/geometry/home`. It then reads the mesh through the registry's `geometry` operation, as the web route will. It writes `<part>.json`, `<part>.html` (three-cad-viewer from jsDelivr) and `<part>.png`. It prints the `mass` check's volume beside the mesh volume, and exits 1 when they differ by more than 0.5%. Cost: docker and one Chromium per part. The plate gives `mass check volume 29509.723 mm^3, mesh volume 29509.926 mm^3, off by 0.0007%`.

Free proofs: `tests/geometry/test_lane.py` (pending, stored, not stored, retry). Docker: `tests/geometry/test_volume.py` (the volume for three parts, a BREP the kernel cannot read). `tests/operations/test_registry.py` proves that the tool list holds only `AGENT` operations.

## Evidence

Look at each `<part>.png`: the part is shaded, with its edges drawn, and the tree lists `variant`. A blank canvas or a page error fails the script.
