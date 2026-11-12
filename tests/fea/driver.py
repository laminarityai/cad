import hashlib
import json
import sys
from dataclasses import replace

from cases import BY_NAME, Case

from cad.checks.container import fea
from cad.checks.container.calculix import SolveFailed, solve
from cad.checks.container.elastic import (
    Face,
    contains,
    extent,
    face_nodes,
    region_faces,
    spread,
    worst_displacement,
    worst_von_mises,
)
from cad.checks.container.kernel import Unreadable, ocp_kernel
from cad.checks.container.mesher import MeshFailed, TetMesh, mesh_pair, tet_mesh
from cad.checks.container.regions import Disc, FarFrom, Plane, Region, Unresolved
from cad.checks.container.vectors import norm, unit

REGION_TOLERANCE = 1e-4


def solved(case: Case, mesh: TetMesh, size_mm: float) -> dict[str, object]:
    tol = REGION_TOLERANCE * extent(mesh)
    fixed = region_faces(mesh, on_faces(mesh, case.fixed, tol), tol)
    loaded = region_faces(mesh, on_faces(mesh, case.loaded, tol), tol)
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


def on_faces[T: Region | FarFrom](mesh: TetMesh, anchor: T, tol: float) -> T:
    """A case names a region by the surfaces its hand calculation assumes, and the check places a
    region by kernel face, so the region takes each face whose triangles all lie on one of those
    surfaces. A disc counts as its whole plane here: the check then keeps the part inside it."""
    if not isinstance(anchor, Region):
        return anchor
    planes = [Plane(p.center, p.normal) if isinstance(p, Disc) else p for p in anchor.patches]
    by_face: dict[int, list[Face]] = {}
    for face, surface in zip(mesh.faces, mesh.surfaces, strict=True):
        by_face.setdefault(surface, []).append(face)
    chosen = frozenset(
        surface
        for surface, faces in by_face.items()
        if all(any(all(contains(p, mesh.nodes[i], tol) for i in f) for p in planes) for f in faces)
    )
    return replace(anchor, faces=chosen)


def main() -> None:
    case = BY_NAME[sys.argv[1]]
    brep = sys.stdin.buffer.read()
    kernel = ocp_kernel()
    shape = kernel.read_brep(brep)
    assert not isinstance(shape, Unreadable), shape.reason
    sizes = fea.mesh_sizes_of(kernel.faces(shape), kernel.inertia(shape))
    meshes = mesh_pair(lambda size, floor: tet_mesh(brep, size, floor), sizes)
    if isinstance(meshes, MeshFailed):
        sys.stdout.write(json.dumps({"failed": meshes.reason}))
        return
    report = {
        "coarse": solved(case, meshes.coarse, sizes.coarse),
        "fine": solved(case, meshes.fine, sizes.fine),
        "over_cap": None if meshes.over_cap is None else meshes.over_cap.reason,
    }
    sys.stdout.write(json.dumps(report))
