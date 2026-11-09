from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field

from cad.briefs import store as briefs
from cad.briefs.model import MadeOf
from cad.briefs.store import BriefState
from cad.geometry import store as meshes
from cad.geometry.model import Stored, UnknownMesh
from cad.operations.model import Audience, Input, Tenant, operation
from cad.operations.research import brief_table
from cad.operations.scorecards import MaterialKey, ScorecardInput, scorecard
from cad.operations.server import NoArguments
from cad.projects.membership import stored_projects
from cad.projects.model import UnknownProject, parse_project_id
from cad.sandbox import image
from cad.scorecard import material
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import MAX_MEMBERS, Member, NotConfirmed
from cad.variants import entry

LIST_PROJECTS = "The signed-in person's projects, newest first, each with its briefs."
PROJECT = "One project: its briefs, each with its proposal count and its confirmed proposal."
VARIANT_SET = (
    "The variant set of a brief: for each slot, its latest variant and every revision the slot "
    "has had. A member's card_etag is the etag of its scorecard for the material: material_key, "
    "or without it the material the person confirmed in a made_of requirement. It is empty when "
    "the variant was never scored for that material. A brief with no confirmed requirements has "
    "an empty set."
)
VIEW = (
    "What the viewer needs for one built variant: the hash that names its BREP, and whether its "
    "mesh is stored. Fetch a stored mesh with the mesh route for that hash."
)
MESH = (
    "The stored mesh of one BREP, in three-cad-viewer's shapes format. A BREP's mesh never "
    "changes, so a client may cache it for good."
)


class ProjectInput(Input):
    project_id: str


class VariantSetInput(Input):
    project_id: str
    brief_id: str
    material_key: MaterialKey | None = None


class VariantInput(Input):
    variant_id: str


class MeshInput(Input):
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
    card_etag: str | None


class VariantSetView(BaseModel):
    project_id: str
    brief_id: str
    decision_sha256: str | None
    limit: int = MAX_MEMBERS
    members: tuple[MemberView, ...]


class VariantView(BaseModel):
    variant_id: str
    brep_sha256: str
    mesh: Literal["tessellated", "failed", "pending"]


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
    found = stored_projects(tenant.roots).get(parse_project_id(arguments.project_id))
    if found is None:
        raise UnknownProject(f"no project {arguments.project_id} is stored")
    return ProjectView(
        project_id=arguments.project_id,
        briefs=tuple(_summary(briefs.read_state(tenant.roots, one.id)) for one in found),
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
    try:
        key = variant_sets.confirmed_key(tenant.roots, brief_id)
    except NotConfirmed:
        return VariantSetView(
            project_id=arguments.project_id, brief_id=brief_id, decision_sha256=None, members=()
        )
    material_key = arguments.material_key or _confirmed_material(tenant, brief_id)
    return VariantSetView(
        project_id=arguments.project_id,
        brief_id=brief_id,
        decision_sha256=key.decision_sha256,
        members=tuple(
            _member(tenant, brief_id, material_key, one)
            for one in variant_sets.members(tenant.roots.projects, key)
        ),
    )


def _confirmed_material(tenant: Tenant, brief_id: str) -> str | None:
    pin = material.pinned_by(briefs.confirmed_requirements(tenant.roots, brief_id))
    if pin is None or not isinstance(pin.target, MadeOf):
        return None
    return brief_table(tenant.roots, brief_id).table.row_key(pin.target.material)


def _member(tenant: Tenant, brief_id: str, material_key: str | None, member: Member) -> MemberView:
    latest = member.latest.built_as
    return MemberView(
        slot=member.slot,
        variant_id=latest,
        revision=len(member.revisions),
        revisions=tuple(
            RevisionView(
                revision=number,
                variant_id=one.built_as,
                code_sha256=one.code_sha256,
                joined_at=one.joined_at,
            )
            for number, one in enumerate(member.revisions, start=1)
        ),
        card_etag=_etag(tenant, brief_id, material_key, latest),
    )


def _etag(tenant: Tenant, brief_id: str, material_key: str | None, variant_id: str) -> str | None:
    if material_key is None:
        return None
    asked = ScorecardInput(variant_id=variant_id, material_key=material_key, brief_id=brief_id)
    try:
        return scorecard(tenant, asked).etag
    except entry.VariantRefused:
        return None


def view(tenant: Tenant, arguments: VariantInput) -> VariantView:
    held = entry.open_entry(tenant.variants, arguments.variant_id, image.image_tag(image.BUILD))
    stored = meshes.read(tenant.geometry, held.brep_sha256)
    return VariantView(
        variant_id=held.id,
        brep_sha256=held.brep_sha256,
        mesh="pending" if stored is None else stored.kind,
    )


def mesh(tenant: Tenant, arguments: MeshInput) -> Stored:
    stored = meshes.read(tenant.geometry, arguments.brep_sha256)
    if stored is None:
        raise UnknownMesh(f"no mesh is stored for BREP {arguments.brep_sha256}")
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
        audience=Audience.PERSON,
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
        output=Stored,
        run=mesh,
    ),
)
