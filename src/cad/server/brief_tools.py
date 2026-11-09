from typing import Annotated, Literal

from mcp.server.mcpserver.tools import Tool
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
from cad.projects.membership import project_for_new_brief
from cad.projects.model import PROJECT_ID, PROJECT_ID_CHARS
from cad.records.roots import Roots
from cad.sandbox import host
from cad.server.refusals import agent_facing

PLAN_MODE = (
    "Plan mode comes first for every brief. Store the user's words with create_brief, unchanged. "
    "Turn them into requirements with propose_requirements, each quoting the words it comes "
    "from. Then call ask_to_confirm with the project_id: only the user can confirm, on one page "
    "that opens on their screen and lists everything waiting on them in the project, and you "
    "cannot answer it. Build no geometry for a brief until ask_to_confirm or list_requirements "
    "says its requirements are confirmed. If the user declines, read their note, revise, and "
    "propose again."
)
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


def brief_tools(roots: Roots) -> list[Tool]:
    def create_brief(
        text: Annotated[str, Field(min_length=1, max_length=MAX_BRIEF_CHARS)],
        project_id: Annotated[
            str | None, Field(max_length=PROJECT_ID_CHARS, pattern=PROJECT_ID.pattern)
        ] = None,
    ) -> BriefCreated:
        with agent_facing():
            project = project_for_new_brief(roots, project_id)
            brief = store.create_brief(roots, text, project)
        return BriefCreated(brief_id=brief.id, project_id=project)

    def propose_requirements(
        brief_id: str,
        requirements: Annotated[
            list[RequirementDraft], Field(min_length=1, max_length=MAX_REQUIREMENTS)
        ],
    ) -> ProposalView:
        drafts = [store.Draft(target=r.target, quote=r.quote) for r in requirements]
        with agent_facing():
            made_of.check_proposed(drafts, host.materials_table().materials)
            project = store.read_brief(roots, brief_id).project
            parts = {one.record.id for one in stored_parts(roots.projects, project)}
            clearances.check_proposed(drafts, parts)
            proposed = store.propose(roots, brief_id, drafts)
            return _view(store.read_state(roots, brief_id), proposed)

    def list_requirements(brief_id: str) -> BriefView:
        with agent_facing():
            state = store.read_state(roots, brief_id)
        confirmed = state.confirmed
        return BriefView(
            brief_id=state.brief.id,
            project_id=state.brief.project,
            text=state.brief.text,
            proposals=[_view(state, p) for p in state.proposals],
            confirmed_proposal=confirmed.proposal.number if confirmed else None,
        )

    return [
        Tool.from_function(create_brief, description=CREATE_BRIEF),
        Tool.from_function(propose_requirements, description=PROPOSE_REQUIREMENTS),
        Tool.from_function(list_requirements, description=LIST_REQUIREMENTS),
    ]
