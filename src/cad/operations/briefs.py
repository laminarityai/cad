from collections.abc import Sequence
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from cad.briefs import assumptions, clearances, made_of, source, store
from cad.briefs.assumptions import MAX_ASSUMPTIONS, Assumption
from cad.briefs.edits import placeholder
from cad.briefs.model import (
    MAX_BRIEF_CHARS,
    MAX_REQUIREMENTS,
    MAX_STATEMENT_CHARS,
    MadeOf,
    PartName,
    Requirement,
    Target,
    deciding_check,
)
from cad.briefs.store import BriefState, ProposalState, Status
from cad.briefs.words import describe, describe_target
from cad.checks.report import QUICK, closure
from cad.context_parts.store import stored_parts
from cad.conversations import store as conversations
from cad.conversations.model import ConversationId, UnknownConversation
from cad.operations.guidance import PLAN_MODE
from cad.operations.model import BOTH, Audience, Input, Tenant, operation
from cad.operations.research import brief_table
from cad.projects.membership import project_for_new_brief
from cad.projects.model import PROJECT_ID, PROJECT_ID_CHARS
from cad.research.overlay import ProjectTable
from cad.research.requests import ResearchRequest, requests_before_scoring

AFTER_PROPOSAL: Final = (
    "You may research it while the user confirms: score_variant reads the stored value."
)

CREATE_BRIEF = (
    "Store a new brief and return its brief id, project id and the text stored. In chat, pass no "
    "text: the server copies the person's newest message, and those words are the brief. From "
    "any other client, pass text, the person's own words verbatim, not a summary or a rewrite: "
    "the person reads this text when they confirm. Create a brief only for a new part: a change "
    "to a part the project already has stays in that part's brief. A project holds every brief "
    "for one job. Omit project_id to start a new project, or, in a chat that has a project, to "
    "add the brief to that project. Pass the project_id an earlier create_brief returned to add "
    "this brief to that project; a brief stays in the project it was created in. Pass name, a "
    'short noun name for the part, such as "Desk box" or "Lid": the person\'s page shows it. '
    + PLAN_MODE
)
PROPOSE_REQUIREMENTS = (
    "If the brief names a material, call list_materials before you propose. Propose the whole "
    "set of requirements for a brief. Each has a target and a quote copied exactly from the "
    "brief. The target kind is closed_solid; max_mass or min_mass with a mass "
    "such as {magnitude: 150, unit: g}; envelope with three edge lengths; measure_limit, which "
    "holds one team check's measure to a limit the user confirms, with check_id, measure, a "
    "comparator (at_most or at_least) and a limit such as {magnitude: 30, unit: cm^3}, and "
    "today the only measure is check_id mass, measure volume, which takes a volume; made_of with a "
    "material, only when the brief names one, quoting its words (at most one per brief). When the "
    "brief names no material, propose no made_of and do not ask the person for one: you choose "
    "it for each variant when you build it. When the brief names one, call "
    "list_materials first, and copy the key of the table's row for that material when it lists "
    "one; for a generic name such as PLA or PETG use the row for that polymer, and the person "
    "confirms the choice on the page. Otherwise give "
    "a key of your own that names it, such as acme-pla-matte. The server stores a material the "
    "table lacks as the project's own row, project- and your key, and the reply's research "
    "asks for each value its checks read; answer it with submit_research. min_safety_factor (a "
    "factor, against yield) or max_deflection (a length), each with a load; "
    "min_clearance or max_clearance with a part, the part_id propose_context_part returned "
    "for this project, and a clearance length, which the fit check decides against that part "
    "with the variant built in the part's frame; or unchecked with a statement, for anything "
    "no check decides. A load has a support, which is holes (a count "
    "and an optional bore diameter), largest_flat or flat_end, and a load, which is far_end or "
    "on_holes (a count and an optional diameter), each with a force such as {magnitude: 49, "
    "unit: N} and a direction: along or across the long axis or the hole_axis, or any. Propose "
    "factor 2 unless the brief states one. Words for where the part is held or loaded that "
    "none of these say are an unchecked requirement. Proposing never confirms: every new row is "
    "proposed until the user confirms the set. A new proposal replaces the old one for "
    "confirmation, and what the user already confirmed stays in force until they confirm the "
    "new set. Proposing the same set again, undecided or confirmed, changes nothing, so it never "
    "asks the person twice. A quote may come from "
    "words the person said after the brief was created. In chat, the server finds them in the "
    "person's messages and adds that message to the brief, so quote it exactly and pass no "
    "said. From any other client, pass the person's new words verbatim as said. Propose every "
    "requirement that should stay in force, with the new one. Propose as a requirement only a "
    "number the person stated, and quote the words that state it. A number the person did not "
    "state, such as a load or a limit you fill in to build, goes under assumptions, a list of "
    "{target, why}: why is one line saying what you assumed and why. The server stores the "
    "assumptions as their own numbered set beside the proposals. Each call's assumptions replace "
    "the earlier set, so pass every assumption that should stay, or an empty list to clear them. "
    "An assumption is never on the confirmation page, never confirmed, and never gets a verdict: "
    "the scorecard lists it under assumptions, with the measure beside the assumed value, and a "
    "check measures against it so you can see how the design does. Say what you assumed in your "
    "reply. Leave requirements out to change only the assumptions: that writes no proposal, so it "
    "never asks the person again and never stops an Auto run. The person turns an assumption "
    "into a target by stating it. An assumption holds a number a check measures, so a made_of, "
    "closed_solid or unchecked target is not one."
)
LIST_REQUIREMENTS = (
    "Show a brief's text, every proposal with its status (proposed, confirmed, declined or "
    "superseded), and which proposal the user last confirmed: its requirements are the only "
    "ones checks will read. A row whose edited_by_user is set holds the number the user typed "
    "on the confirmation page in place of the proposed one; its quote still shows the brief's "
    "own words. assumptions lists the agent's assumptions in force: no verdict ever rests on "
    "one."
)


class RequirementDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Target
    quote: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]


class AssumptionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Target
    why: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]


class AssumptionRow(BaseModel):
    target: Target
    plain: str
    why: str
    check: str | None


class BriefCreated(BaseModel):
    brief_id: str
    project_id: str
    text: str


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


class Proposed(BaseModel):
    """The newest proposal, with its requirements, or no proposal when the brief has none. A call
    with no requirements writes none and shows the newest. `assumptions` is what the agent
    assumed and `research` asks for each value of the made_of material that the set's checks read
    and the table lacks."""

    brief_id: str
    proposal: int | None
    status: Status | None
    requirements: list[RequirementRow]
    assumptions: list[AssumptionRow] = Field(default=[], exclude_if=lambda one: not one)
    research: tuple[ResearchRequest, ...] = Field(default=(), exclude_if=lambda one: not one)


class BriefView(BaseModel):
    brief_id: str
    project_id: str
    text: str
    name: str | None
    proposals: list[ProposalView]
    confirmed_proposal: int | None
    assumptions: list[AssumptionRow] = Field(default=[], exclude_if=lambda one: not one)


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


def _assumed(held: assumptions.AssumptionSet | None) -> list[AssumptionRow]:
    return [
        AssumptionRow(
            target=one.target,
            plain=describe_target(one.target),
            why=one.why,
            check=deciding_check(one.target),
        )
        for one in (held.assumptions if held else ())
    ]


def _made_of_requests(
    table: ProjectTable, brief_id: str, drafts: Sequence[store.Draft]
) -> tuple[ResearchRequest, ...]:
    key = next((d.target.material for d in drafts if isinstance(d.target, MadeOf)), None)
    if key is None or table.problem is not None:
        return ()
    checks = [spec.id for spec in QUICK]
    checks += [check for d in drafts if (check := deciding_check(d.target)) is not None]
    fields = sorted({str(one) for spec in closure(checks) for one in spec.takes})
    return requests_before_scoring(table.table, key, fields, brief_id, AFTER_PROPOSAL)


def _user_edit(proposed: Requirement, confirmed: Requirement) -> UserEdit | None:
    before, after = placeholder(proposed), placeholder(confirmed)
    if proposed.id == confirmed.id or before is None or after is None:
        return None
    return UserEdit(proposed=before, confirmed=after)


class CreateBriefInput(Input):
    text: Annotated[str, Field(min_length=1, max_length=MAX_BRIEF_CHARS)] | None = None
    name: PartName | None = None
    project_id: Annotated[
        str | None, Field(max_length=PROJECT_ID_CHARS, pattern=PROJECT_ID.pattern)
    ] = None


class ProposeRequirementsInput(Input):
    brief_id: str
    requirements: (
        Annotated[list[RequirementDraft], Field(min_length=1, max_length=MAX_REQUIREMENTS)] | None
    ) = None
    assumptions: Annotated[list[AssumptionDraft], Field(max_length=MAX_ASSUMPTIONS)] | None = None
    said: Annotated[str, Field(min_length=1, max_length=MAX_BRIEF_CHARS)] | None = None


class ListRequirementsInput(Input):
    brief_id: str


def create_brief(tenant: Tenant, arguments: CreateBriefInput) -> BriefCreated:
    first = source.first_words(tenant.conversations, tenant.conversation, arguments.text)
    cid = tenant.conversation
    asked = arguments.project_id
    if asked is None and cid is not None:
        asked = _project_of(tenant, cid)
    project = project_for_new_brief(tenant.roots, asked)
    brief = store.create_brief(
        tenant.roots, first.text, project, first.transcript_seq, arguments.name
    )
    if cid is not None:
        conversations.started(tenant.conversations, cid, project)
    return BriefCreated(brief_id=brief.id, project_id=project, text=brief.text)


def _project_of(tenant: Tenant, cid: ConversationId) -> str | None:
    try:
        return conversations.read(tenant.conversations, cid).project_id
    except UnknownConversation:
        return None


def propose_requirements(tenant: Tenant, arguments: ProposeRequirementsInput) -> Proposed:
    if arguments.requirements is None and arguments.assumptions is None:
        raise store.BadProposal(
            "pass requirements, assumptions or both: with neither there is nothing to store"
        )
    project = store.read_brief(tenant.roots, arguments.brief_id).project
    parts = {one.record.id for one in stored_parts(tenant.roots.projects, project)}
    drafts: list[store.Draft] = []
    table = brief_table(tenant.roots, arguments.brief_id)
    if arguments.requirements is not None:
        words = source.later_words(tenant.conversations, tenant.conversation, arguments.said)
        drafts = [store.Draft(target=r.target, quote=r.quote) for r in arguments.requirements]
        clearances.check_proposed([one.target for one in drafts], parts)
        drafts = made_of.with_row_keys(drafts, table.table)
        store.propose(tenant.roots, arguments.brief_id, drafts, words)
    held = assumptions.in_force(tenant.roots, arguments.brief_id)
    if arguments.assumptions is not None:
        held = assumptions.assume(
            tenant.roots,
            arguments.brief_id,
            [Assumption(target=one.target, why=one.why) for one in arguments.assumptions],
            parts,
        )
    state = store.read_state(tenant.roots, arguments.brief_id)
    shown = None if state.latest is None else _view(state, state.latest)
    return Proposed(
        brief_id=state.brief.id,
        proposal=None if shown is None else shown.proposal,
        status=None if shown is None else shown.status,
        requirements=[] if shown is None else shown.requirements,
        assumptions=_assumed(held),
        research=_made_of_requests(table, arguments.brief_id, drafts),
    )


def list_requirements(tenant: Tenant, arguments: ListRequirementsInput) -> BriefView:
    state = store.read_state(tenant.roots, arguments.brief_id)
    confirmed = state.confirmed
    return BriefView(
        brief_id=state.brief.id,
        project_id=state.brief.project,
        text=state.brief.text,
        name=state.brief.name,
        proposals=[_view(state, p) for p in state.proposals],
        confirmed_proposal=confirmed.proposal.number if confirmed else None,
        assumptions=_assumed(assumptions.in_force(tenant.roots, arguments.brief_id)),
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
        output=Proposed,
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
