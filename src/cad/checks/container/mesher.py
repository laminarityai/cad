import importlib
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Protocol, cast

from cad.checks.container.vectors import Point

WALL_ELEMENTS: Final = 1.0
MIN_SIZE_MM: Final = 0.2
EXTENT_ELEMENTS: Final = 20.0
FINE_RATIO: Final = 1.5
CURVATURE_ELEMENTS: Final = 24
NODE_CAP: Final = 150_000
FLOOR_FRACTION: Final = 0.5
MESH_CHANGE_LIMIT: Final = 0.03

TET10: Final = 11
TRIANGLE6: Final = 9
# gmsh numbers the last two midside nodes of a 10-node tetrahedron on edges (2,3) and (1,3);
# CalculiX's C3D10 puts edge (1,3) first.
GMSH_TO_CCX: Final = (0, 1, 2, 3, 4, 5, 6, 7, 9, 8)


@dataclass(frozen=True, slots=True)
class MeshSizes:
    coarse: float
    fine: float


def mesh_sizes(wall_mm: float, extent_mm: float) -> MeshSizes:
    coarse = min(max(wall_mm / WALL_ELEMENTS, MIN_SIZE_MM), extent_mm / EXTENT_ELEMENTS)
    return MeshSizes(coarse, coarse / FINE_RATIO)


@dataclass(frozen=True, slots=True)
class TetMesh:
    """`tets` holds 10 node indices per element in CalculiX C3D10 order; `faces` holds the
    boundary's 6-node triangles, corners first."""

    nodes: tuple[Point, ...]
    tets: tuple[tuple[int, ...], ...]
    faces: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class MeshFailed:
    reason: str


@dataclass(frozen=True, slots=True)
class OverCap(MeshFailed):
    """A mesh with more nodes than the solve may take."""


@dataclass(frozen=True, slots=True)
class MeshPair:
    """The two meshes the check compares. `over_cap` is set when the meshes refined to the part's
    curvature held too many nodes, so these two keep every element at least `FLOOR_FRACTION` of
    the coarse size."""

    coarse: TetMesh
    fine: TetMesh
    over_cap: OverCap | None


type Mesher = Callable[[float, float], TetMesh | MeshFailed]


class _Option(Protocol):
    def setNumber(self, name: str, value: float) -> None: ...


class _Occ(Protocol):
    def importShapes(self, fileName: str) -> object: ...
    def synchronize(self) -> None: ...


class _Mesh(Protocol):
    def generate(self, dim: int) -> None: ...
    def getNodes(self) -> tuple[Sequence[int], Sequence[float], Sequence[float]]: ...
    def getElementsByType(self, elementType: int) -> tuple[Sequence[int], Sequence[int]]: ...


class _Model(Protocol):
    @property
    def occ(self) -> _Occ: ...
    @property
    def mesh(self) -> _Mesh: ...


class _Gmsh(Protocol):
    @property
    def option(self) -> _Option: ...
    @property
    def model(self) -> _Model: ...
    def initialize(self, argv: list[str], readConfigFiles: bool) -> None: ...
    def finalize(self) -> None: ...


OPTIONS: Final = {
    "General.Terminal": 0,
    "General.NumThreads": 1,
    "Mesh.MaxNumThreads1D": 1,
    "Mesh.MaxNumThreads2D": 1,
    "Mesh.MaxNumThreads3D": 1,
    "Mesh.Algorithm3D": 1,
    "Mesh.RandomSeed": 1,
    "Mesh.ElementOrder": 2,
    "Mesh.MeshSizeFromCurvature": CURVATURE_ELEMENTS,
}


def mesh_pair(mesh: Mesher, sizes: MeshSizes) -> MeshPair | MeshFailed:
    """Mesh at both sizes. When either mesh is over the node cap, mesh both again with one floor,
    `FLOOR_FRACTION` of the coarse size, under which no element goes. Where the curvature rule
    would go below it, as on a small fillet, both meshes then have the same size, so there the
    coarse against fine change no longer tests refinement. The operator accepted that on
    2026-11-11 so that thin, filleted parts get a verdict. Only a part over the cap is meshed
    differently."""
    refined = _pair(mesh, sizes, 0.0)
    if not isinstance(refined, OverCap):
        return refined
    floored = _pair(mesh, sizes, FLOOR_FRACTION * sizes.coarse)
    if isinstance(floored, MeshFailed):
        return MeshFailed(f"{refined.reason}; {floored.reason}")
    return MeshPair(floored.coarse, floored.fine, refined)


def _pair(mesh: Mesher, sizes: MeshSizes, floor_mm: float) -> MeshPair | MeshFailed:
    meshes: list[TetMesh] = []
    for size in (sizes.coarse, sizes.fine):
        made = mesh(size, floor_mm)
        if isinstance(made, MeshFailed):
            under = f" with no element under {floor_mm:g} mm" if floor_mm else ""
            verb = " " if isinstance(made, OverCap) else " failed: "
            return replace(made, reason=f"the mesh at {size:g} mm{under}{verb}{made.reason}")
        meshes.append(made)
    coarse, fine = meshes
    return MeshPair(coarse, fine, None)


def tet_mesh(
    brep: bytes, size_mm: float, floor_mm: float = 0.0, node_cap: int = NODE_CAP
) -> TetMesh | MeshFailed:
    """The surface is meshed first, alone, so a size whose surface is already over the cap stops
    before its volume mesh can outgrow the check's memory. The volume mesh is made afresh, the same
    as without that first pass."""
    surface = _generated(brep, size_mm, floor_mm, 2, _surface_nodes)
    if isinstance(surface, MeshFailed):
        return surface
    if surface > node_cap:
        reason = f"has {surface} nodes on its surface alone, above the cap of {node_cap}"
        return OverCap(reason)
    return _generated(brep, size_mm, floor_mm, 3, lambda mesh: _read(mesh, node_cap))


def _generated[T](
    brep: bytes, size_mm: float, floor_mm: float, dim: int, read: Callable[[_Mesh], T]
) -> T | MeshFailed:
    gmsh = cast(_Gmsh, importlib.import_module("gmsh"))
    gmsh.initialize([], False)
    try:
        for name, value in OPTIONS.items():
            gmsh.option.setNumber(name, value)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size_mm)
        if floor_mm:
            gmsh.option.setNumber("Mesh.MeshSizeMin", floor_mm)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shape.brep"
            path.write_bytes(brep)
            gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.generate(dim)
        return read(gmsh.model.mesh)
    except Exception as error:
        return MeshFailed(f"gmsh failed: {type(error).__name__}: {error}")
    finally:
        gmsh.finalize()


def _surface_nodes(mesh: _Mesh) -> int:
    _, face_nodes = mesh.getElementsByType(TRIANGLE6)
    return len({int(tag) for tag in face_nodes})


def _read(mesh: _Mesh, node_cap: int) -> TetMesh | MeshFailed:
    _, tet_nodes = mesh.getElementsByType(TET10)
    if len(tet_nodes) == 0:
        return MeshFailed("gmsh made no 10-node tetrahedra")
    used = sorted({int(tag) for tag in tet_nodes})
    if len(used) > node_cap:
        return OverCap(f"has {len(used)} nodes, above the cap of {node_cap}")
    index = {tag: i for i, tag in enumerate(used)}
    tags, flat, _ = mesh.getNodes()
    where = {int(tag): i for i, tag in enumerate(tags)}
    nodes = tuple(
        (float(flat[3 * k]), float(flat[3 * k + 1]), float(flat[3 * k + 2]))
        for k in (where[tag] for tag in used)
    )
    tets = tuple(
        tuple(index[int(tet_nodes[start + j])] for j in GMSH_TO_CCX)
        for start in range(0, len(tet_nodes), 10)
    )
    _, face_nodes = mesh.getElementsByType(TRIANGLE6)
    faces = tuple(
        tuple(index[int(tag)] for tag in face_nodes[start : start + 6])
        for start in range(0, len(face_nodes), 6)
    )
    return TetMesh(nodes, tets, faces)
