from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from cad.agent_checks import limits
from cad.briefs import assumptions, carry, clearances, described, made_of, said, source, store
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
from cad.briefs.origins import FILE_ID_PATTERN
from cad.briefs.store import BriefState, ProposalState, Status
from cad.briefs.words import describe, describe_target
from cad.checks.report import QUICK, closure
from cad.confirmations.requirements import plain_names
from cad.context_parts.store import stored_parts
from cad.conversations import store as conversations
from cad.conversations.model import ConversationId, UnknownConversation
from cad.operations.guidance import BUILD_FIRST, PROPOSE_REQUIREMENTS
from cad.operations.model import BOTH, Audience, Input, Tenant, operation
from cad.operations.research import brief_table
from cad.projects.membership import project_for_new_brief
from cad.projects.model import PROJECT_ID, PROJECT_ID_CHARS, ProjectId, ProjectRefused
from cad.research.overlay import ProjectTable
from cad.research.requests import ResearchRequest, requests_before_scoring
from cad.uploads import quotes
from cad.variant_sets.stressed import has_stress_result

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
    + BUILD_FIRST
)
LIST_REQUIREMENTS = (
    "Show a brief's text, every proposal with its status (proposed, confirmed, declined or "
    "superseded), and which proposal the user last confirmed: its requirements are the only "
    "ones checks will read. A row whose edited_by_user is set holds the number the user typed "
    "on the confirmation page in place of the proposed one; its quote still shows the brief's "
    "own words. assumptions lists the agent's assumptions in force: no verdict ever rests on "
    "one."
)


type RequirementIdText = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]


class RequirementDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Target
    quote: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]
    file_id: Annotated[str, Field(pattern=FILE_ID_PATTERN)] | None = None


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


def _view(state: BriefState, proposed: ProposalState, names: Mapping[str, str]) -> ProposalView:
    confirmed = state.confirmed
    in_force = {r.id for r in confirmed.requirements} if confirmed else set[str]()
    changed = carry.edited(state, proposed.proposal.number)
    return ProposalView(
        brief_id=state.brief.id,
        proposal=proposed.proposal.number,
        status=proposed.status,
        requirements=[
            RequirementRow(
                requirement=r,
                plain=describe(r, names),
                check=deciding_check(r.target),
                status="confirmed" if r.id in in_force else "proposed",
                edited_by_user=_user_edit(changed.get(r.id, was), r),
            )
            for was, r in zip(proposed.proposal.requirements, proposed.requirements, strict=True)
        ],
    )


def _assumed(
    held: assumptions.AssumptionSet | None, names: Mapping[str, str]
) -> list[AssumptionRow]:
    return [
        AssumptionRow(
            target=one.target,
            plain=describe_target(one.target, names),
            why=one.why,
            check=deciding_check(one.target),
        )
        for one in (held.assumptions if held else ())
    ]


def _made_of_requests(
    table: ProjectTable, brief_id: str, targets: Sequence[Target]
) -> tuple[ResearchRequest, ...]:
    key = next((one.material for one in targets if isinstance(one, MadeOf)), None)
    if key is None or table.problem is not None:
        return ()
    checks = [spec.id for spec in QUICK]
    checks += [check for one in targets if (check := deciding_check(one)) is not None]
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
    remove: (
        Annotated[list[RequirementIdText], Field(min_length=1, max_length=MAX_REQUIREMENTS)] | None
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
    if (
        arguments.requirements is None
        and arguments.remove is None
        and arguments.assumptions is None
    ):
        raise store.BadProposal(
            "pass requirements, remove, assumptions or a mix: with none there is nothing to store"
        )
    project = store.read_brief(tenant.roots, arguments.brief_id).project
    parts = {one.record.id for one in stored_parts(tenant.roots.projects, project)}
    drafts: list[store.Draft] = []
    targets: list[Target] = []
    table = brief_table(tenant.roots, arguments.brief_id)
    if arguments.requirements is not None or arguments.remove is not None:
        words = source.later_words(tenant.conversations, tenant.conversation, arguments.said)
        text = store.read_brief(tenant.roots, arguments.brief_id).text
        drafts = [
            _draft(tenant, project, index, one, lambda quote: said.typed(text, quote, words))
            for index, one in enumerate(arguments.requirements or ())
        ]
        clearances.check_proposed([one.target for one in drafts], parts)
        limits.check_proposed(
            tenant.roots.projects, project, arguments.brief_id, [one.target for one in drafts]
        )
        state = store.read_state(tenant.roots, arguments.brief_id)
        described.check_proposed(
            state,
            [one.target for one in drafts],
            [one.target for one in carry.kept_after(state, arguments.remove or ())],
            lambda: has_stress_result(tenant.roots, tenant.variants, arguments.brief_id),
        )
        drafts = made_of.with_row_keys(drafts, table.table)
        stored = store.propose(
            tenant.roots, arguments.brief_id, drafts, words, arguments.remove or ()
        )
        targets = [one.target for one in stored.requirements]
    held = assumptions.in_force(tenant.roots, arguments.brief_id)
    if arguments.assumptions is not None:
        held = assumptions.assume(
            tenant.roots,
            arguments.brief_id,
            [Assumption(target=one.target, why=one.why) for one in arguments.assumptions],
            parts,
        )
    state = store.read_state(tenant.roots, arguments.brief_id)
    names = plain_names(tenant.roots, arguments.brief_id)
    shown = None if state.latest is None else _view(state, state.latest, names)
    return Proposed(
        brief_id=state.brief.id,
        proposal=None if shown is None else shown.proposal,
        status=None if shown is None else shown.status,
        requirements=[] if shown is None else shown.requirements,
        assumptions=_assumed(held, names),
        research=_made_of_requests(table, arguments.brief_id, targets),
    )


def _draft(
    tenant: Tenant,
    project: ProjectId,
    index: int,
    one: RequirementDraft,
    typed: Callable[[str], bool],
) -> store.Draft:
    if one.file_id is None:
        return store.Draft(target=one.target, quote=one.quote)
    try:
        return quotes.draft(
            tenant.roots.projects, project, one.target, one.quote, one.file_id, typed
        )
    except ProjectRefused as refused:
        raise store.BadProposal(f"requirements[{index}]: {refused}") from refused


def list_requirements(tenant: Tenant, arguments: ListRequirementsInput) -> BriefView:
    state = store.read_state(tenant.roots, arguments.brief_id)
    confirmed = state.confirmed
    names = plain_names(tenant.roots, arguments.brief_id)
    return BriefView(
        brief_id=state.brief.id,
        project_id=state.brief.project,
        text=state.brief.text,
        name=state.brief.name,
        proposals=[_view(state, p, names) for p in state.proposals],
        confirmed_proposal=confirmed.proposal.number if confirmed else None,
        assumptions=_assumed(assumptions.in_force(tenant.roots, arguments.brief_id), names),
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
