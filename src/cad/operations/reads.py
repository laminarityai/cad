from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field

from cad.briefs import store as briefs
from cad.briefs.store import BriefState, ConfirmedSet
from cad.context_parts.store import newest_parts
from cad.geometry import job
from cad.geometry import store as meshes
from cad.geometry.bodies import BodyFaces, body_faces
from cad.geometry.lane import TESSELLATIONS
from cad.geometry.model import Tessellated, UnknownMesh
from cad.operations.model import BOTH, Audience, Input, Tenant, operation
from cad.operations.research import brief_table
from cad.operations.scorecards import MaterialKey, ScorecardInput, scorecard
from cad.operations.server import NoArguments
from cad.projects.membership import stored_projects
from cad.projects.model import UnknownProject, parse_project_id
from cad.sandbox import image
from cad.sandbox.outcome import Areas, on_faces
from cad.scorecard import material, score
from cad.scorecard.material import BodyMaterialUse, MaterialUse, ScorecardSnapshot
from cad.tables.materials import MaterialsTable
from cad.uploads.store import documents
from cad.uploads.views import ContextPartView, DocumentView, document_view, part_view
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import MAX_MEMBERS, BodyChoice, MaterialMissing, Member, Option
from cad.variants import entry

LIST_PROJECTS = "The signed-in person's projects, newest first, each with its briefs."
PROJECT = (
    "One project: its briefs, each with its proposal count and its confirmed proposal, and the "
    "newest record of each part a brief must fit with."
)
VARIANT_SET = (
    "The variant set of a brief: for each slot, its latest variant and every revision the slot "
    "has had. A member's option is the label the agent gave its slot and how it differs from "
    "the others; it is empty when none was given. A member's material is the one its card "
    "uses and what set it: the made_of "
    "requirement the person confirmed, or the agent, with the reason it recorded; it is empty "
    "when neither named one. A member's card_etag is the etag of its scorecard for that "
    "material, or for material_key when you pass it. It is empty when the variant was never "
    "scored for that material. For a variant of named bodies, body_materials is each body's "
    "material and what set it, as its card states, or as the slot records until it is scored. "
    "material_name is the name a person reads for the material. A "
    "brief nothing was built for has an empty set."
)
VIEW = (
    "What the viewer needs for one built variant: the hash that names its BREP, whether its mesh "
    "is tessellated, failed or pending, and once it is tessellated, the mesh_url to fetch it from. "
    "A build starts its mesh, and this read starts it too when no job is making it, so pending "
    "means a job is running: read it again. Once the mesh is tessellated, areas are the names "
    "and colours the build code gave sets of faces, numbered as the mesh numbers them, and "
    "empty when it gave none or named a face the mesh does not have. They are how the model "
    "looks, and no check reads them."
)
MESH = (
    "The mesh of one BREP made by one tessellator version, in three-cad-viewer's shapes format. "
    "Those two name the bytes, so a client may cache them for good. A version that is no longer "
    "current, or a BREP that did not tessellate, is not found, so take the URL from the view."
)
MESH_PATH: Final = "/v1/geometry/{version}/{brep_sha256}.json"


class ProjectInput(Input):
    project_id: str


class VariantSetInput(Input):
    project_id: str
    brief_id: str
    material_key: MaterialKey | None = None


class VariantInput(Input):
    variant_id: str


class MeshInput(Input):
    version: Annotated[str, Field(pattern=r"^[0-9a-f]{12}$")]
    brep_sha256: Annotated[str, Field(pattern=meshes.SHA256.pattern)]


class ProjectSummary(BaseModel):
    project_id: str
    created_at: datetime
    brief_ids: tuple[str, ...]


class ProjectList(BaseModel):
    projects: tuple[ProjectSummary, ...]


class BriefSummary(BaseModel):
    brief_id: str
    created_at: datetime
    proposals: int
    confirmed_proposal: int | None


class ProjectView(BaseModel):
    project_id: str
    briefs: tuple[BriefSummary, ...]
    context_parts: tuple[ContextPartView, ...]
    documents: tuple[DocumentView, ...]


class RevisionView(BaseModel):
    revision: int
    variant_id: str
    code_sha256: str
    joined_at: datetime


class MemberView(BaseModel):
    slot: int
    variant_id: str
    revision: int
    revisions: tuple[RevisionView, ...]
    material: MaterialUse | None
    option: Option | None
    material_name: str | None
    card_etag: str | None
    body_materials: tuple[BodyMaterialUse, ...] = ()


class VariantSetView(BaseModel):
    project_id: str
    brief_id: str
    limit: int = MAX_MEMBERS
    members: tuple[MemberView, ...]


class VariantView(BaseModel):
    variant_id: str
    brep_sha256: str
    mesh: Literal["tessellated", "failed", "pending"]
    mesh_url: str | None
    areas: Areas
    bodies: tuple[BodyFaces, ...] = ()


def list_projects(tenant: Tenant, arguments: NoArguments) -> ProjectList:
    del arguments
    return ProjectList(
        projects=tuple(
            ProjectSummary(
                project_id=project,
                created_at=found[0].created_at,
                brief_ids=tuple(one.id for one in found),
            )
            for project, found in stored_projects(tenant.roots).items()
        )
    )


def project(tenant: Tenant, arguments: ProjectInput) -> ProjectView:
    project_id = parse_project_id(arguments.project_id)
    found = stored_projects(tenant.roots).get(project_id)
    if found is None:
        raise UnknownProject(f"no project {arguments.project_id} is stored")
    return ProjectView(
        project_id=arguments.project_id,
        briefs=tuple(_summary(briefs.read_state(tenant.roots, one.id)) for one in found),
        context_parts=tuple(
            part_view(one) for one in newest_parts(tenant.roots.projects, project_id)
        ),
        documents=tuple(document_view(one) for one in documents(tenant.roots.projects, project_id)),
    )


def _summary(state: BriefState) -> BriefSummary:
    confirmed = state.confirmed
    return BriefSummary(
        brief_id=state.brief.id,
        created_at=state.brief.created_at,
        proposals=len(state.proposals),
        confirmed_proposal=confirmed.proposal.number if confirmed else None,
    )


def variant_set(tenant: Tenant, arguments: VariantSetInput) -> VariantSetView:
    brief_id = arguments.brief_id
    if briefs.read_brief(tenant.roots, brief_id).project != arguments.project_id:
        raise UnknownProject(f"brief {brief_id} is not in project {arguments.project_id}")
    key = variant_sets.set_key(tenant.roots, brief_id)
    confirmed = briefs.confirmed_requirements(tenant.roots, brief_id)
    table = brief_table(tenant.roots, brief_id).table
    pinned = material.pins(confirmed, table)
    return VariantSetView(
        project_id=arguments.project_id,
        brief_id=brief_id,
        members=tuple(
            _member(tenant, brief_id, arguments.material_key, confirmed, pinned, table, one)
            for one in variant_sets.members(tenant.roots.projects, key)
        ),
    )


def _member(
    tenant: Tenant,
    brief_id: str,
    asked: str | None,
    confirmed: ConfirmedSet | None,
    pinned: material.Pins,
    table: MaterialsTable,
    member: Member,
) -> MemberView:
    latest = member.latest
    tag = image.image_tag(image.BUILD)
    shown = variant_sets.current_id(tenant.variants, latest, tag)
    choice = latest.material
    key = _whole_variant_pin(pinned) or (None if choice is None else choice.key)
    names = _body_names(tenant, shown)
    card = _card(tenant, brief_id, asked or key, shown, bool(names))
    each = (
        _unscored_body_materials(names, latest.materials, confirmed, pinned, table)
        if card is None
        else card.body_materials
    )
    return MemberView(
        slot=member.slot,
        variant_id=shown,
        revision=len(member.revisions),
        revisions=tuple(
            RevisionView(
                revision=number,
                variant_id=variant_sets.current_id(tenant.variants, one, tag),
                code_sha256=one.code_sha256,
                joined_at=one.joined_at,
            )
            for number, one in enumerate(member.revisions, start=1)
        ),
        material=None if key is None else material.used(key, confirmed, choice),
        option=latest.option,
        material_name=None if key is None else table.name_of(key),
        card_etag=None if card is None else card.etag,
        body_materials=each,
    )


def _whole_variant_pin(pinned: material.Pins) -> str | None:
    every = pinned.get(None)
    if any(key != every for key in pinned.values()):
        return None
    return every


def _body_names(tenant: Tenant, variant_id: str) -> tuple[str, ...]:
    try:
        held = entry.open_entry(tenant.variants, variant_id, image.image_tag(image.BUILD))
    except entry.VariantRefused:
        return ()
    return tuple(body.name for body in held.bodies)


def _unscored_body_materials(
    names: Sequence[str],
    chosen: Sequence[BodyChoice],
    confirmed: ConfirmedSet | None,
    pinned: material.Pins,
    table: MaterialsTable,
) -> tuple[BodyMaterialUse, ...]:
    kept = {one.body: one for one in chosen}
    each: list[BodyMaterialUse] = []
    for name in names or kept:
        choice = kept.get(name)
        key = material.pin_for(pinned, name) or (None if choice is None else choice.key)
        if key is not None:
            each.append(
                BodyMaterialUse(
                    body=name,
                    name=table.name_of(key),
                    **dict(material.used(key, confirmed, choice, name)),
                )
            )
    return tuple(each)


def _card(
    tenant: Tenant, brief_id: str, material_key: str | None, variant_id: str, each_body: bool
) -> ScorecardSnapshot | None:
    if material_key is None and not each_body:
        return None
    asked = ScorecardInput(variant_id=variant_id, material_key=material_key, brief_id=brief_id)
    try:
        return scorecard(tenant, asked)
    except (entry.VariantRefused, score.NotScored, MaterialMissing):
        return None


def view(tenant: Tenant, arguments: VariantInput) -> VariantView:
    held = entry.open_entry(tenant.variants, arguments.variant_id, image.image_tag(image.BUILD))
    stored = TESSELLATIONS.start(tenant.geometry, held)
    tessellated = isinstance(stored, Tessellated)
    return VariantView(
        variant_id=held.id,
        brep_sha256=held.brep_sha256,
        mesh="pending" if stored is None else stored.kind,
        mesh_url=MESH_PATH.format(version=job.VERSION, brep_sha256=held.brep_sha256)
        if tessellated
        else None,
        areas=on_faces(held.areas, len(stored.topology["faces"])) if tessellated else (),
        bodies=body_faces(held.bodies, stored.solid_faces) if tessellated else (),
    )


def mesh(tenant: Tenant, arguments: MeshInput) -> Tessellated:
    stored = meshes.read(tenant.geometry, arguments.brep_sha256)
    if not isinstance(stored, Tessellated) or arguments.version != job.VERSION:
        raise UnknownMesh(
            f"no mesh of tessellator {arguments.version} is stored for BREP {arguments.brep_sha256}"
        )
    return stored


OPERATIONS: Final = (
    operation(
        name="list_projects",
        audience=Audience.PERSON,
        description=LIST_PROJECTS,
        input=NoArguments,
        output=ProjectList,
        run=list_projects,
    ),
    operation(
        name="project",
        audience=Audience.PERSON,
        description=PROJECT,
        input=ProjectInput,
        output=ProjectView,
        run=project,
    ),
    operation(
        name="variant_set",
        audience=BOTH,
        description=VARIANT_SET,
        input=VariantSetInput,
        output=VariantSetView,
        run=variant_set,
    ),
    operation(
        name="view",
        audience=Audience.PERSON,
        description=VIEW,
        input=VariantInput,
        output=VariantView,
        run=view,
    ),
    operation(
        name="mesh",
        audience=Audience.PERSON,
        description=MESH,
        input=MeshInput,
        output=Tessellated,
        run=mesh,
    ),
)
