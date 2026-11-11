"""Resolve what the person picked against the revision's geometry and sign it."""

import secrets
from datetime import UTC, datetime
from typing import Final

from cad.geometry.container.wire import EdgeFacts, FaceFacts, TopologyWire
from cad.geometry.lane import TESSELLATIONS
from cad.geometry.model import Tessellated, TessellationFailed
from cad.operations.model import Tenant
from cad.projects.model import ProjectId
from cad.sandbox import image
from cad.selections import store
from cad.selections.model import (
    BoundingBox,
    Neighbour,
    Picked,
    SelectedEdge,
    SelectedFace,
    SelectedPart,
    SelectionNote,
    SelectionRecord,
    SelectionRefused,
)
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import SetKey
from cad.variants import entry

MESH_WAIT_SECONDS: Final = 5.0


def mint(tenant: Tenant, project: ProjectId, picked: Picked) -> SelectionRecord:
    """Find the slot and revision of the project that shows `picked.variant_id`, read the
    topology of its BREP, check every picked number is in range, describe each pick, then sign
    and store the record. Raises SelectionRefused with a message the person can read when the
    variant is not in the project, its mesh is not ready, or a number is out of range."""
    tag = image.image_tag(image.BUILD)
    key, slot, revision = _revision_of(tenant, project, picked.variant_id, tag)
    held = entry.open_entry(tenant.variants, picked.variant_id, tag)
    read = TESSELLATIONS.read(tenant.geometry, held, wait_seconds=MESH_WAIT_SECONDS)
    if isinstance(read, TessellationFailed):
        raise SelectionRefused(f"this design has no mesh to pick from: {read.reason}")
    if not isinstance(read, Tessellated):
        raise SelectionRefused("the 3D view of this design is still being prepared; try again")
    topology = read.topology
    _in_range(picked, topology)
    box = read.shapes["bb"]
    record = SelectionRecord(
        selection_id=f"sel-{secrets.token_hex(8)}",
        project_id=project,
        brief_id=key.brief_id,
        slot=slot,
        revision=revision,
        variant_id=picked.variant_id,
        brep_sha256=held.brep_sha256,
        faces=tuple(_face(topology, index) for index in picked.faces),
        edges=tuple(_edge(topology, index) for index in picked.edges),
        part=SelectedPart(
            faces=len(topology["faces"]),
            edges=len(topology["edges"]),
            bounding_box=BoundingBox(
                min_mm=(box["xmin"], box["ymin"], box["zmin"]),
                max_mm=(box["xmax"], box["ymax"], box["zmax"]),
            ),
        )
        if picked.part
        else None,
        made_at=datetime.now(UTC),
    )
    store.save(tenant.roots.projects, record)
    return record


def note(record: SelectionRecord) -> SelectionNote:
    """The transcript's note: the id, and a summary such as "2 faces" or "the whole part"."""
    return SelectionNote(
        selection_id=record.selection_id,
        summary=_summary(len(record.faces), len(record.edges)),
        brief_id=record.brief_id,
        slot=record.slot,
        revision=record.revision,
    )


def _summary(faces: int, edges: int) -> str:
    parts = [
        f"{count} {name}{'' if count == 1 else 's'}"
        for count, name in ((faces, "face"), (edges, "edge"))
        if count
    ]
    return " and ".join(parts) or "the whole part"


def _revision_of(
    tenant: Tenant, project: ProjectId, variant_id: str, tag: str
) -> tuple[SetKey, int, int]:
    found: list[tuple[SetKey, int, int, bool]] = []
    for key, member in variant_sets.project_slots(tenant.roots.projects, project):
        for number, revision in enumerate(member.revisions, start=1):
            if variant_id in (revision.built_as, revision.live_id(tag)):
                found.append((key, member.slot, number, revision is member.latest))
    if not found:
        raise SelectionRefused(
            f"variant {variant_id} is not a design of this project, so there is nothing to pick"
        )
    key, slot, number, _ = max(found, key=lambda one: one[3])
    return key, slot, number


def _in_range(picked: Picked, topology: TopologyWire) -> None:
    for kind, indices, held in (
        ("face", picked.faces, len(topology["faces"])),
        ("edge", picked.edges, len(topology["edges"])),
    ):
        for index in indices:
            if index >= held:
                raise SelectionRefused(
                    f"{kind} {index} is not on this design, which has {held} {kind}s"
                )


def _face(topology: TopologyWire, index: int) -> SelectedFace:
    facts = topology["faces"][index]
    touching = {face for edge in facts["edges"] for face in topology["edges"][edge]["faces"]} - {
        index
    }
    return SelectedFace(
        face=index,
        type=facts["type"],
        area_mm2=facts["area"],
        center_mm=facts["center"],
        normal=facts["normal"],
        radius_mm=facts["radius"],
        axis=facts["axis"],
        adjacent=_neighbours(topology, touching),
    )


def _edge(topology: TopologyWire, index: int) -> SelectedEdge:
    facts: EdgeFacts = topology["edges"][index]
    return SelectedEdge(
        edge=index,
        type=facts["type"],
        length_mm=facts["length"],
        center_mm=facts["center"],
        direction=facts["direction"],
        radius_mm=facts["radius"],
        between=_neighbours(topology, set(facts["faces"])),
    )


def _neighbours(topology: TopologyWire, faces: set[int]) -> tuple[Neighbour, ...]:
    return tuple(_neighbour(index, topology["faces"][index]) for index in sorted(faces))


def _neighbour(index: int, facts: FaceFacts) -> Neighbour:
    return Neighbour(
        face=index, type=facts["type"], normal=facts["normal"], radius_mm=facts["radius"]
    )
