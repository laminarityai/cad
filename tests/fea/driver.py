import hashlib
import json
import sys

from cases import BY_NAME, Case

from cad.checks.container.calculix import SolveFailed, solve
from cad.checks.container.elastic import (
    extent,
    face_nodes,
    norm,
    region_faces,
    spread,
    unit,
    worst_displacement,
    worst_von_mises,
)
from cad.checks.container.mesher import MeshFailed, mesh_sizes, tet_mesh

REGION_TOLERANCE = 1e-4


def solved(case: Case, brep: bytes, size_mm: float) -> dict[str, object]:
    mesh = tet_mesh(brep, size_mm)
    if isinstance(mesh, MeshFailed):
        return {"failed": mesh.reason}
    tol = REGION_TOLERANCE * extent(mesh)
    fixed = region_faces(mesh, case.fixed, tol)
    loaded = region_faces(mesh, case.loaded, tol)
    if not fixed or not loaded:
        return {"failed": f"{len(fixed)} fixed and {len(loaded)} loaded triangles"}
    unit_load = spread(mesh, loaded, unit(case.force))
    fields = solve(mesh, case.material, face_nodes(fixed), (unit_load,))
    if isinstance(fields, SolveFailed):
        return {"failed": fields.reason}
    scale = norm(case.force)
    return {
        "size_mm": size_mm,
        "nodes": len(mesh.nodes),
        "max_displacement": scale * worst_displacement([f.displacement for f in fields]),
        "max_von_mises": scale * worst_von_mises([f.stress for f in fields]),
        "field_sha256": hashlib.sha256(repr(fields).encode()).hexdigest(),
    }


def main() -> None:
    case = BY_NAME[sys.argv[1]]
    brep = sys.stdin.buffer.read()
    sizes = mesh_sizes(case.thinnest_wall_mm, case.largest_extent_mm)
    report = {"coarse": solved(case, brep, sizes.coarse), "fine": solved(case, brep, sizes.fine)}
    sys.stdout.write(json.dumps(report))
