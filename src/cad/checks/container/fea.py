import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from cad.checks.container import anchors, closed_solid, features, interference, terms
from cad.checks.container.calculix import Material, NodalField, SolveFailed
from cad.checks.container.check import (
    DIMENSIONLESS,
    Background,
    CheckModule,
    Fem,
    Subject,
    finding,
    measure,
    no_shape,
    required_pass,
)
from cad.checks.container.elastic import (
    extent,
    face_nodes,
    region_faces,
    spread,
    surfaces_of,
    worst_displacement,
    worst_von_mises,
)
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.kernel import FaceInfo, Inertia, Shape, Unreadable
from cad.checks.container.mesher import (
    MESH_CHANGE_LIMIT,
    MeshFailed,
    MeshPair,
    MeshSizes,
    OverCap,
    TetMesh,
    mesh_pair,
    mesh_sizes,
)
from cad.checks.container.regions import FAR_FRACTION, Bore, Candidate, Plane, Resolved, Unresolved
from cad.checks.container.vectors import Point, cross, dot, norm, sub
from cad.checks.container.wire import FindingWire, MeasuredWire, SourceLiteral, WhereWire

ID = "fea"
_END_DEG: Final = math.degrees(features.END_CONE_RAD)
_FAR_DEG: Final = math.degrees(anchors.FAR_CONE_RAD)
FORMULA = (
    "linear static finite element analysis of the confirmed load case: 10-node tetrahedra "
    "meshed at min(max(wall, 0.2 mm), extent / 20) and again 1.5 times finer, wall = 2 * "
    "volume / surface area, refined to the part's curvature; when either mesh would have more "
    "than 150,000 nodes, both are meshed again with no element under half the coarse size, so "
    "near a small fillet both meshes have the same size and their change does not test "
    "refinement there; a flat "
    f"end is the flat face that bounds the part, faces within {_END_DEG:g} degrees of the long "
    "axis and "
    "lies farthest along it, with the faces flush with it, and when the two largest volume "
    "spreads tie each tied direction gives ends; the far end is the flat face that bounds the "
    f"part, faces within {_FAR_DEG:g} degrees of the line from the support to the centre of mass "
    "and lies farthest along it, or, when no flat face does, the surface within "
    f"{FAR_FRACTION:.1%} of the largest "
    "reach along that line; the supports' surface nodes are fixed and the force is spread "
    "uniformly over the loaded faces; a direction the load case leaves free goes to the worst "
    "case over unit solves; max_displacement and max_von_mises are the fine mesh's largest, "
    "von Mises stress within 0.5 * bore diameter of a support hole is reported as "
    "support_max_von_mises and not judged; safety_factor = yield_strength / max_von_mises; "
    "unknown when closed_solid or interference does not pass, the load case does not resolve, "
    "E or Poisson's ratio is unknown, the mesh or solve fails, the two meshes' max_displacement "
    "differ by more than 3%, or max_displacement exceeds 5% of the part's extent"
)
SOURCES: tuple[SourceLiteral, ...] = (
    {
        "url": "http://www.dhondt.de/ccx_2.20.pdf",
        "title": "CalculiX CrunchiX USER'S MANUAL version 2.20",
        "page": "6.2.7 Ten-node tetrahedral element (C3D10), p. 97",
        "retrieved": date(2026, 11, 8),
        "standard": None,
        "quote": (
            "The C3D10 element is especially attractive because of the existence of fully "
            "automatic tetrahedral meshers."
        ),
    },
)
MEASURES = {
    "max_von_mises": "MPa",
    "max_displacement": "mm",
    "safety_factor": DIMENSIONLESS,
    "displacement_change": DIMENSIONLESS,
    "support_max_von_mises": "MPa",
    "mesh_size": "mm",
    "elastic_modulus": "MPa",
    "poisson_ratio": DIMENSIONLESS,
    "yield_strength": "MPa",
}
TAKES = frozenset({Input.ELASTIC_MODULUS, Input.POISSON_RATIO, Input.YIELD_STRENGTH})
READS = {
    "elastic_modulus": Input.ELASTIC_MODULUS,
    "poisson_ratio": Input.POISSON_RATIO,
    "yield_strength": Input.YIELD_STRENGTH,
}
REQUIRES: tuple[CheckModule, ...] = (closed_solid, interference)
BUDGET = Background(wall_seconds=600, memory_mb=2048, tmpfs_mb=768)

DISPLACEMENT_ERROR: Final = 0.05
STRESS_ERROR: Final = 0.07
ERROR_BOUNDS = {
    "max_displacement": DISPLACEMENT_ERROR,
    "max_von_mises": STRESS_ERROR,
    "safety_factor": STRESS_ERROR / (1 - STRESS_ERROR),
}

KEEP_OUT_DIAMETERS: Final = 0.5
CLAMPED_FACE_NOTE: Final = (
    "Peak stress next to a clamped face can read high on short parts, so the stress and the "
    "safety factor here are conservative."
)
LARGE_DISPLACEMENT_FRACTION: Final = 0.05
STIFFER: Final = (
    "make it stiffer where it bends, for example thicker or deeper there, shorter, or in a "
    "stiffer material, and score it again"
)
TOL_FRACTION: Final = 1e-4


@dataclass(frozen=True, slots=True)
class Peaks:
    displacement: float
    von_mises: float
    support_von_mises: float


@dataclass(frozen=True, slots=True)
class Pair:
    """One candidate's unit solve: its peaks, and the faces its support fixed and its load
    pressed on."""

    peaks: Peaks
    where: WhereWire


@dataclass(frozen=True, slots=True)
class Solved:
    size_mm: float
    peaks: Peaks
    where: WhereWire
    """The faces of the candidate with the largest von Mises stress, which is the one whose stress
    the result reports."""


@dataclass(frozen=True, slots=True)
class Unsolved:
    reason: str


def run(subject: Subject) -> FindingWire:
    shape = subject.shape
    if isinstance(shape, Unreadable):
        return no_shape(shape)
    unmet = required_pass(subject, REQUIRES, "load")
    if unmet is not None:
        return unmet
    case = subject.inputs.load_case()
    return assessed(subject, shape, terms.of_wire(case), case["load"]["force_n"])


def assessed(subject: Subject, shape: Shape, case: terms.LoadCase, force: float) -> FindingWire:
    """The check on a load case written in terms, once the wire is parsed and the shape is known
    to be one closed solid."""
    echoed, material, yield_mpa = _material(subject.inputs)
    if isinstance(material, str):
        return finding("unknown", material, *echoed)
    part = features.geometry(subject.kernel, shape)
    resolved = anchors.resolve(case, part)
    if isinstance(resolved, Unresolved):
        return finding("unknown", f"the load case does not resolve: {resolved.reason}", *echoed)
    sizes = mesh_sizes_of(part.faces, part.inertia)
    meshes = mesh_pair(subject.fem.mesh, sizes)
    if isinstance(meshes, MeshFailed):
        return finding("unknown", meshes.reason, *echoed)
    unmatched = _unmatched(meshes, len(part.faces))
    if unmatched is not None:
        return finding("unknown", unmatched, *echoed)
    coarse = solve_at(subject.fem, meshes.coarse, sizes.coarse, resolved, material, force)
    if isinstance(coarse, Unsolved):
        return finding("unknown", coarse.reason, *echoed)
    fine = solve_at(subject.fem, meshes.fine, sizes.fine, resolved, material, force)
    if isinstance(fine, Unsolved):
        return finding("unknown", fine.reason, *echoed)
    clamped = clamps_a_face(resolved)
    return judged(
        coarse, fine, yield_mpa, features.extent(part.inertia), echoed, clamped, meshes.over_cap
    )


def _unmatched(meshes: MeshPair, kernel_faces: int) -> str | None:
    """Supports and loads are picked by kernel face index and applied by gmsh surface tag, so the
    two must count the same faces."""
    for mesh in (meshes.coarse, meshes.fine):
        surfaces = len(set(mesh.surfaces))
        if surfaces != kernel_faces:
            return (
                f"the mesh has triangles on {surfaces} surfaces where the kernel reads "
                f"{kernel_faces} faces, so the support and load cannot be placed"
            )
    return None


def mesh_sizes_of(faces: Sequence[FaceInfo], inertia: Inertia) -> MeshSizes:
    wall = 2 * inertia.volume / sum(face.area for face in faces)
    return mesh_sizes(wall, features.extent(inertia))


def clamps_a_face(resolved: Resolved) -> bool:
    return any(
        isinstance(patch, Plane)
        for candidate in resolved.candidates
        for patch in candidate.support.patches
    )


def judged(
    coarse: Solved,
    fine: Solved,
    yield_mpa: float | None,
    part_extent: float,
    echoed: Sequence[MeasuredWire],
    clamped_face: bool,
    over_cap: OverCap | None,
) -> FindingWire:
    change = abs(fine.peaks.displacement - coarse.peaks.displacement) / fine.peaks.displacement
    floored = (
        ""
        if over_cap is None
        else (
            "; both meshes keep every element at least half the coarse size, because "
            f"{over_cap.reason}"
        )
    )
    measured = [
        *echoed,
        measure("mesh_size", fine.size_mm, "mm"),
        measure("max_displacement", fine.peaks.displacement, "mm"),
        measure("max_von_mises", fine.peaks.von_mises, "MPa"),
        measure("support_max_von_mises", fine.peaks.support_von_mises, "MPa"),
        measure("displacement_change", change, DIMENSIONLESS),
    ]
    if change > MESH_CHANGE_LIMIT:
        return finding(
            "unknown",
            f"the meshes at {coarse.size_mm:g} mm and {fine.size_mm:g} mm differ by "
            f"{change:.1%} in max_displacement, over the {MESH_CHANGE_LIMIT:.0%} limit{floored}",
            *measured,
            where=fine.where,
        )
    if fine.peaks.displacement > LARGE_DISPLACEMENT_FRACTION * part_extent:
        return finding(
            "unknown",
            f"the part bends {fine.peaks.displacement:.3g} mm under this load, over "
            f"{LARGE_DISPLACEMENT_FRACTION:.0%} of its {part_extent:.3g} mm size, which is too "
            f"far for a linear analysis to give a verdict; {STIFFER}{floored}",
            *measured,
            where=fine.where,
        )
    reason = (
        f"solved at {coarse.size_mm:g} mm and {fine.size_mm:g} mm; max_displacement differs "
        f"by {change:.1%}{floored}"
    )
    if yield_mpa is None:
        reason = f"{reason}; no yield strength, so no safety factor"
    if clamped_face:
        reason = f"{reason}. {CLAMPED_FACE_NOTE}"
    if yield_mpa is None:
        return finding("pass", reason, *measured, where=fine.where)
    return finding(
        "pass",
        reason,
        *measured,
        measure("safety_factor", yield_mpa / fine.peaks.von_mises, DIMENSIONLESS),
        where=fine.where,
    )


def solve_at(
    fem: Fem, mesh: TetMesh, size_mm: float, resolved: Resolved, material: Material, force_n: float
) -> Solved | Unsolved:
    pairs: list[Pair] = []
    for candidate in resolved.candidates:
        found = _unit_solve(fem, mesh, candidate, material)
        if isinstance(found, Unsolved):
            return found
        pairs.append(found)
    peaks = [one.peaks for one in pairs]
    deciding = max(pairs, key=lambda one: one.peaks.von_mises)
    return Solved(
        size_mm,
        Peaks(
            force_n * max(one.displacement for one in peaks),
            force_n * max(one.von_mises for one in peaks),
            force_n * max(one.support_von_mises for one in peaks),
        ),
        deciding.where,
    )


def _unit_solve(
    fem: Fem, mesh: TetMesh, candidate: Candidate, material: Material
) -> Pair | Unsolved:
    tol = TOL_FRACTION * extent(mesh)
    fixed = region_faces(mesh, candidate.support, tol)
    if isinstance(fixed, Unresolved):
        return Unsolved(f"the support has no mesh faces: {fixed.reason}")
    loaded = region_faces(mesh, candidate.load, tol)
    if isinstance(loaded, Unresolved):
        return Unsolved(f"the load has no mesh faces: {loaded.reason}")
    unit_loads = [spread(mesh, loaded, way) for way in candidate.basis]
    fields = fem.solve(mesh, material, face_nodes(fixed), unit_loads)
    if isinstance(fields, SolveFailed):
        return Unsolved(f"the solve failed: {fields.reason}")
    bores = [patch for patch in candidate.support.patches if isinstance(patch, Bore)]
    near = [any(_near(bore, node) for bore in bores) for node in mesh.nodes]
    peaks = Peaks(
        worst_displacement([field.displacement for field in fields]),
        _worst_stress(fields, [i for i, inside in enumerate(near) if not inside]),
        _worst_stress(fields, [i for i, inside in enumerate(near) if inside]),
    )
    where: WhereWire = {
        "support": list(surfaces_of(mesh, fixed)),
        "load": list(surfaces_of(mesh, loaded)),
    }
    return Pair(peaks, where)


def _worst_stress(fields: Sequence[NodalField], nodes: Sequence[int]) -> float:
    if not nodes:
        return 0.0
    return worst_von_mises([[field.stress[i] for i in nodes] for field in fields])


def _near(bore: Bore, node: Point) -> bool:
    reach = KEEP_OUT_DIAMETERS * 2 * bore.radius
    offset = sub(node, bore.origin)
    along = dot(offset, bore.axis)
    radial = norm(cross(offset, bore.axis))
    return radial <= bore.radius + reach and bore.t0 - reach <= along <= bore.t1 + reach


def _material(inputs: Inputs) -> tuple[list[MeasuredWire], Material | str, float | None]:
    echoed: list[MeasuredWire] = []
    known: dict[str, float] = {}
    unknown: dict[str, str] = {}
    for name, wanted in READS.items():
        value = inputs.value(wanted)
        if value["kind"] == "unknown":
            unknown[name] = value["reason"]
        else:
            known[name] = value["magnitude"]
            echoed.append(measure(name, value["magnitude"], MEASURES[name]))
    stiffness = [unknown[name] for name in ("elastic_modulus", "poisson_ratio") if name in unknown]
    if stiffness:
        return echoed, "; ".join(stiffness), None
    material = Material(known["elastic_modulus"], known["poisson_ratio"])
    return echoed, material, known.get("yield_strength")
