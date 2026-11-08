import math
from collections.abc import Callable, Sequence

from cad.checks.container.anchors import Bore, FarFrom, Patch, Plane, Region, Unresolved
from cad.checks.container.mesher import TetMesh
from cad.checks.container.vectors import Point, cross, dot, norm, sub

type Stress = tuple[float, float, float, float, float, float]
"""xx, yy, zz, xy, yz, zx, as CalculiX orders them."""
type Matrix = tuple[tuple[float, ...], ...]
type Face = tuple[int, ...]


def contains(patch: Patch, point: Point, tol: float) -> bool:
    match patch:
        case Plane(origin, normal):
            return abs(dot(sub(point, origin), normal)) <= tol
        case Bore(origin, axis, radius, t0, t1):
            offset = sub(point, origin)
            along = dot(offset, axis)
            return abs(norm(cross(offset, axis)) - radius) <= tol and t0 - tol <= along <= t1 + tol


def extent(mesh: TetMesh) -> float:
    return max(
        max(node[axis] for node in mesh.nodes) - min(node[axis] for node in mesh.nodes)
        for axis in range(3)
    )


def region_faces(
    mesh: TetMesh, anchor: Region | FarFrom, tol: float
) -> tuple[Face, ...] | Unresolved:
    """The boundary triangles whose 6 nodes all lie in one of the region's patches, or all lie at
    least the far cutoff from the center."""
    match anchor:
        case Region(patches):
            faces = tuple(
                face
                for face in mesh.faces
                if any(all(contains(p, mesh.nodes[i], tol) for i in face) for p in patches)
            )
        case FarFrom(center):
            surface = [mesh.nodes[i] for i in face_nodes(mesh.faces)]
            cutoff = anchor.cutoff(surface) - tol
            faces = tuple(
                face
                for face in mesh.faces
                if all(norm(sub(mesh.nodes[i], center)) >= cutoff for i in face)
            )
    if not faces:
        return Unresolved("no mesh triangle lies wholly on the anchored surface")
    return faces


def face_nodes(faces: Sequence[Face]) -> frozenset[int]:
    return frozenset(i for face in faces for i in face)


def area(mesh: TetMesh, face: Face) -> float:
    a, b, c = (mesh.nodes[i] for i in face[:3])
    return norm(cross(sub(b, a), sub(c, a))) / 2


def spread(mesh: TetMesh, faces: Sequence[Face], force: Point) -> dict[int, Point]:
    """Consistent nodal loads of `force` spread as a uniform traction over the faces: on a 6-node
    triangle a uniform traction puts nothing on the corners and a third of the triangle's share
    on each midside node."""
    areas = [area(mesh, face) for face in faces]
    total = sum(areas)
    loads: dict[int, Point] = {}
    for face, share in zip(faces, areas, strict=True):
        weight = share / total / 3
        for i in face[3:]:
            x, y, z = loads.get(i, (0.0, 0.0, 0.0))
            loads[i] = (x + weight * force[0], y + weight * force[1], z + weight * force[2])
    return loads


def von_mises_form(s: Stress, t: Stress) -> float:
    """The symmetric bilinear form whose value at (s, s) is the squared von Mises stress."""
    normal = s[0] * t[0] + s[1] * t[1] + s[2] * t[2]
    mixed = s[0] * t[1] + s[1] * t[0] + s[1] * t[2] + s[2] * t[1] + s[2] * t[0] + s[0] * t[2]
    shear = s[3] * t[3] + s[4] * t[4] + s[5] * t[5]
    return normal - mixed / 2 + 3 * shear


def von_mises(s: Stress) -> float:
    return math.sqrt(max(von_mises_form(s, s), 0.0))


def largest_eigenvalue(m: Matrix) -> float:
    """Of a symmetric matrix of size 1, 2 or 3, in closed form."""
    match len(m):
        case 1:
            return m[0][0]
        case 2:
            mean = (m[0][0] + m[1][1]) / 2
            return mean + math.hypot((m[0][0] - m[1][1]) / 2, m[0][1])
        case _:
            return _largest_of_3(m)


def _largest_of_3(m: Matrix) -> float:
    off = m[0][1] ** 2 + m[0][2] ** 2 + m[1][2] ** 2
    q = (m[0][0] + m[1][1] + m[2][2]) / 3
    p = math.sqrt(((m[0][0] - q) ** 2 + (m[1][1] - q) ** 2 + (m[2][2] - q) ** 2 + 2 * off) / 6)
    if p == 0:
        return q
    b = tuple(tuple((m[i][j] - (q if i == j else 0)) / p for j in range(3)) for i in range(3))
    half_det = (
        b[0][0] * (b[1][1] * b[2][2] - b[1][2] * b[2][1])
        - b[0][1] * (b[1][0] * b[2][2] - b[1][2] * b[2][0])
        + b[0][2] * (b[1][0] * b[2][1] - b[1][1] * b[2][0])
    ) / 2
    return q + 2 * p * math.cos(math.acos(min(max(half_det, -1.0), 1.0)) / 3)


def worst_displacement(fields: Sequence[Sequence[Point]]) -> float:
    """`fields[j][i]` is the displacement of node i under a unit load along the j-th vector of an
    orthonormal basis of the load's directions. Returns the largest displacement of any node under
    a unit load in the worst direction of that span: the largest singular value of each node's
    3 x k matrix."""
    return max(
        math.sqrt(max(largest_eigenvalue(_gram(per_load, dot)), 0.0))
        for per_load in zip(*fields, strict=True)
    )


def worst_von_mises(stresses: Sequence[Sequence[Stress]]) -> float:
    """As `worst_displacement`, for the von Mises stress of the superposed stress tensors."""
    return max(
        math.sqrt(max(largest_eigenvalue(_gram(per_load, von_mises_form)), 0.0))
        for per_load in zip(*stresses, strict=True)
    )


def _gram[T](vectors: Sequence[T], form: Callable[[T, T], float]) -> Matrix:
    return tuple(tuple(form(a, b) for b in vectors) for a in vectors)
