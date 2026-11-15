"""The parts a person supplied that a variant's build placed, as the viewer draws them
(ADR-0012). No check reads a placement."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel

from cad.context_parts.store import newest_parts, stored_brep
from cad.geometry import job
from cad.geometry import store as meshes
from cad.geometry.lane import TESSELLATIONS
from cad.geometry.model import Stored, Tessellated
from cad.projects.model import ProjectId, parse_project_id
from cad.records.roots import Roots
from cad.sandbox.outcome import PartPlacement, PartUse

MESH_PATH: Final = "/v1/geometry/{version}/{brep_sha256}.json"
type MeshState = Literal["tessellated", "failed", "pending"]


class Component(BaseModel):
    """One supplied part and each copy of it the build placed, at build123d's
    `Location(at, rotate)`. Its mesh is the part in its own frame, read like a variant's."""

    part_id: str
    name: str
    brep_sha256: str
    mesh: MeshState
    mesh_url: str | None
    placements: tuple[PartPlacement, ...]


@dataclass(frozen=True, slots=True)
class _Part:
    brep: bytes
    brep_sha256: str


def mesh_state(stored: Stored | None) -> tuple[MeshState, str | None]:
    if stored is None:
        return "pending", None
    if isinstance(stored, Tessellated):
        return stored.kind, MESH_PATH.format(version=job.VERSION, brep_sha256=stored.brep_sha256)
    return stored.kind, None


def components(roots: Roots, geometry: Path, uses: tuple[PartUse, ...]) -> tuple[Component, ...]:
    """Each part the build placed, by the SHA-256 its signed record names. Its mesh is started
    when none is stored, and is failed when the project has lost that BREP."""
    placed = [use for use in uses if use.placements]
    names: dict[ProjectId, dict[str, str]] = {
        project: {one.record.id: one.record.name for one in newest_parts(roots.projects, project)}
        for project in {parse_project_id(use.project) for use in placed}
    }
    each: list[Component] = []
    for use in placed:
        mesh, mesh_url = _meshed(roots.projects, geometry, use)
        name = names[parse_project_id(use.project)].get(use.part_id, use.part_id)
        each.append(
            Component(
                part_id=use.part_id,
                name=name,
                brep_sha256=use.brep_sha256,
                mesh=mesh,
                mesh_url=mesh_url,
                placements=use.placements,
            )
        )
    return tuple(each)


def _meshed(projects: Path, geometry: Path, use: PartUse) -> tuple[MeshState, str | None]:
    stored = meshes.read(geometry, use.brep_sha256)
    if stored is None:
        brep = stored_brep(projects, use)
        if brep is None or hashlib.sha256(brep).hexdigest() != use.brep_sha256:
            return "failed", None
        stored = TESSELLATIONS.start(geometry, _Part(brep, use.brep_sha256))
    return mesh_state(stored)
