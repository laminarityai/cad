from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from cad.briefs import clearances, made_of, store
from cad.briefs.edits import placeholder
from cad.briefs.model import (
    MAX_BRIEF_CHARS,
    MAX_REQUIREMENTS,
    MAX_STATEMENT_CHARS,
    Requirement,
    Target,
    deciding_check,
)
from cad.briefs.store import BriefState, ProposalState, Status
from cad.briefs.words import describe
from cad.context_parts.store import stored_parts
from cad.operations.guidance import PLAN_MODE
from cad.operations.model import BOTH, Audience, Input, Tenant, operation
from cad.projects.membership import project_for_new_brief
from cad.projects.model import PROJECT_ID, PROJECT_ID_CHARS
from cad.sandbox import host

CREATE_BRIEF = (
    "Store the user's brief, their own words verbatim, and return its brief id and project id. "
    "Do not summarize or rewrite it: the user reads this text when they confirm. A project "
    "holds every brief for one job. Omit project_id to start a new project. Pass the "
    "project_id an earlier create_brief returned to add this brief to that project; a brief "
    "stays in the project it was created in. " + PLAN_MODE
)
PROPOSE_REQUIREMENTS = (
    "Propose the whole set of requirements for a brief. Each has a target and a quote copied "
    "exactly from the brief. The target kind is closed_solid; max_mass or min_mass with a mass "
    "such as {magnitude: 150, unit: g}; envelope with three edge lengths; measure_limit, which "
    "holds one team check's measure to a limit the user confirms, with check_id, measure, a "
    "comparator (at_most or at_least) and a limit such as {magnitude: 30, unit: cm^3}, and "
    "today the only measure is check_id mass, measure volume, which takes a volume; made_of with a "
    "material, only when the brief names one, quoting its words and copying the key exactly from "
    "list_materials (never guess a near match; at most one per brief); min_safety_factor (a "
    "factor, against yield) or max_deflection (a length), each with a load; min_clearance or "
    "max_clearance with a part, the part_id propose_context_part returned for this project, "
    "and a clearance length, which the fit check decides against that part with the variant "
    "built in the part's frame; or unchecked with a statement, for anything no check decides. "
    "A load has a support, which is holes (a count "
    "and an optional bore diameter), largest_flat or flat_end, and a load, which is far_end or "
    "on_holes (a count and an optional diameter), each with a force such as {magnitude: 49, "
    "unit: N} and a direction: along or across the long axis or the hole_axis, or any. Propose "
    "factor 2 unless the brief states one. Words for where the part is held or loaded that "
    "none of these say are an unchecked requirement. Proposing never confirms: every new row is "
    "proposed until the user confirms the set. A new proposal replaces the old one for "
    "confirmation, and what the user already confirmed stays in force until they confirm the "
    "new set. Proposing the same undecided set again changes nothing."
)
LIST_REQUIREMENTS = (
    "Show a brief's text, every proposal with its status (proposed, confirmed, declined or "
    "superseded), and which proposal the user last confirmed: its requirements are the only "
    "ones checks will read. A row whose edited_by_user is set holds the number the user typed "
    "on the confirmation page in place of the proposed one; its quote still shows the brief's "
    "own words."
)


class RequirementDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Target
    quote: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]


class BriefCreated(BaseModel):
    brief_id: str
    project_id: str


class UserEdit(BaseModel):
    proposed: str
    confirmed: str


class RequirementRow(BaseModel):
    requirement: Requirement
    plain: str
    check: str | None
    status: Literal["proposed", "confirmed"]
    edited_by_user: UserEdit | None


class ProposalView(BaseModel):
    brief_id: str
    proposal: int
    status: Status
    requirements: list[RequirementRow]


class BriefView(BaseModel):
    brief_id: str
    project_id: str
    text: str
    proposals: list[ProposalView]
    confirmed_proposal: int | None


def _view(state: BriefState, proposed: ProposalState) -> ProposalView:
    confirmed = state.confirmed
    in_force = {r.id for r in confirmed.requirements} if confirmed else set[str]()
    return ProposalView(
        brief_id=state.brief.id,
        proposal=proposed.proposal.number,
        status=proposed.status,
        requirements=[
            RequirementRow(
                requirement=r,
                plain=describe(r),
                check=deciding_check(r.target),
                status="confirmed" if r.id in in_force else "proposed",
                edited_by_user=_user_edit(was, r),
            )
            for was, r in zip(proposed.proposal.requirements, proposed.requirements, strict=True)
        ],
    )


def _user_edit(proposed: Requirement, confirmed: Requirement) -> UserEdit | None:
    before, after = placeholder(proposed), placeholder(confirmed)
    if proposed.id == confirmed.id or before is None or after is None:
        return None
    return UserEdit(proposed=before, confirmed=after)


class CreateBriefInput(Input):
    text: Annotated[str, Field(min_length=1, max_length=MAX_BRIEF_CHARS)]
    project_id: Annotated[
        str | None, Field(max_length=PROJECT_ID_CHARS, pattern=PROJECT_ID.pattern)
    ] = None


class ProposeRequirementsInput(Input):
    brief_id: str
    requirements: Annotated[
        list[RequirementDraft], Field(min_length=1, max_length=MAX_REQUIREMENTS)
    ]


class ListRequirementsInput(Input):
    brief_id: str


def create_brief(tenant: Tenant, arguments: CreateBriefInput) -> BriefCreated:
    project = project_for_new_brief(tenant.roots, arguments.project_id)
    brief = store.create_brief(tenant.roots, arguments.text, project)
    return BriefCreated(brief_id=brief.id, project_id=project)


def propose_requirements(tenant: Tenant, arguments: ProposeRequirementsInput) -> ProposalView:
    drafts = [store.Draft(target=r.target, quote=r.quote) for r in arguments.requirements]
    made_of.check_proposed(drafts, host.materials_table().materials)
    project = store.read_brief(tenant.roots, arguments.brief_id).project
    clearances.check_proposed(
        drafts, {one.record.id for one in stored_parts(tenant.roots.projects, project)}
    )
    proposed = store.propose(tenant.roots, arguments.brief_id, drafts)
    return _view(store.read_state(tenant.roots, arguments.brief_id), proposed)


def list_requirements(tenant: Tenant, arguments: ListRequirementsInput) -> BriefView:
    state = store.read_state(tenant.roots, arguments.brief_id)
    confirmed = state.confirmed
    return BriefView(
        brief_id=state.brief.id,
        project_id=state.brief.project,
        text=state.brief.text,
        proposals=[_view(state, p) for p in state.proposals],
        confirmed_proposal=confirmed.proposal.number if confirmed else None,
    )


OPERATIONS: Final = (
    operation(
        name="create_brief",
        audience=Audience.AGENT,
        description=CREATE_BRIEF,
        input=CreateBriefInput,
        output=BriefCreated,
        run=create_brief,
    ),
    operation(
        name="propose_requirements",
        audience=Audience.AGENT,
        description=PROPOSE_REQUIREMENTS,
        input=ProposeRequirementsInput,
        output=ProposalView,
        run=propose_requirements,
    ),
    operation(
        name="list_requirements",
        audience=BOTH,
        description=LIST_REQUIREMENTS,
        input=ListRequirementsInput,
        output=BriefView,
        run=list_requirements,
    ),
)
