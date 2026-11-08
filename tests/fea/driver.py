import hashlib
import json
import sys

from cases import BY_NAME, Case, PlateLoadPatch

from cad.checks.container.anchors import FarFrom, Plane, Region, Unresolved
from cad.checks.container.calculix import SolveFailed, solve
from cad.checks.container.elastic import (
    Face,
    extent,
    face_nodes,
    region_faces,
    spread,
    worst_displacement,
    worst_von_mises,
)
from cad.checks.container.mesher import MeshFailed, TetMesh, mesh_sizes, tet_mesh
from cad.checks.container.vectors import norm, sub, unit

REGION_TOLERANCE = 1e-4


def solved(case: Case, brep: bytes, size_mm: float) -> dict[str, object]:
    mesh = tet_mesh(brep, size_mm)
    if isinstance(mesh, MeshFailed):
        return {"failed": mesh.reason}
    tol = REGION_TOLERANCE * extent(mesh)
    fixed = region_faces(mesh, case.fixed, tol)
    loaded = selected(mesh, case.loaded, tol)
    if isinstance(fixed, Unresolved) or isinstance(loaded, Unresolved):
        return {"failed": f"fixed: {fixed}, loaded: {loaded}"}
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


def selected(
    mesh: TetMesh, anchor: Region | FarFrom | PlateLoadPatch, tol: float
) -> tuple[Face, ...] | Unresolved:
    if not isinstance(anchor, PlateLoadPatch):
        return region_faces(mesh, anchor, tol)
    plane = region_faces(mesh, Region((Plane(anchor.center, anchor.normal),), anchor.center), tol)
    if isinstance(plane, Unresolved):
        return plane
    inside = tuple(
        face
        for face in plane
        if all(norm(sub(mesh.nodes[i], anchor.center)) <= anchor.radius + tol for i in face)
    )
    return inside or Unresolved("no mesh triangle lies wholly inside the load patch")


def main() -> None:
    case = BY_NAME[sys.argv[1]]
    brep = sys.stdin.buffer.read()
    sizes = mesh_sizes(case.thinnest_wall_mm, case.largest_extent_mm)
    report = {"coarse": solved(case, brep, sizes.coarse), "fine": solved(case, brep, sizes.fine)}
    sys.stdout.write(json.dumps(report))
