"""The four brief tools. None of them can write a decision: only the confirmation page can."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from pydantic import BaseModel, Field

from cad.briefs import store
from cad.briefs.ballot import Desk
from cad.briefs.model import (
    MAX_BRIEF_CHARS,
    MAX_REQUIREMENTS,
    MAX_STATEMENT_CHARS,
    Declined,
    Requirement,
    Target,
    deciding_check,
    describe,
)
from cad.briefs.store import BriefRefused, BriefState, BriefStoreUnusable, ProposalState, Status

PLAN_MODE = (
    "Plan mode comes first for every brief. Store the user's words with create_brief, unchanged. "
    "Turn them into requirements with propose_requirements, each quoting the words it comes "
    "from. Then call confirm_requirements: only the user can confirm, on a page that opens on "
    "their screen, and you cannot answer it. Build no geometry for a brief until "
    "confirm_requirements or list_requirements says its requirements are confirmed. If the user "
    "declines, read their note, revise, and propose again."
)
CREATE_BRIEF = (
    "Store the user's brief, their own words verbatim, and return its brief id. Do not "
    "summarize or rewrite it: the user reads this text when they confirm. " + PLAN_MODE
)
PROPOSE_REQUIREMENTS = (
    "Propose the whole set of requirements for a brief. Each has a target and a quote copied "
    "exactly from the brief. The target kind is closed_solid; max_mass or min_mass with a mass "
    "such as {magnitude: 150, unit: g}; envelope with three edge lengths; or unchecked with a "
    "statement, for anything no check decides. Proposing never confirms: every new row is "
    "proposed until the user confirms the set. A new proposal replaces the old one for "
    "confirmation, and what the user already confirmed stays in force until they confirm the "
    "new set. Proposing the same undecided set again changes nothing."
)
CONFIRM_REQUIREMENTS = (
    "Ask the user to confirm the brief's newest proposed requirements on a page that opens in "
    "their browser. Waits up to about 20 seconds, then returns confirmed, declined with the "
    "user's note, or pending. pending is not an answer: tell the user the page is waiting for "
    "them and call again once they say they answered. Calling again opens the same page again; "
    "it never confirms anything."
)
LIST_REQUIREMENTS = (
    "Show a brief's text, every proposal with its status (proposed, confirmed, declined or "
    "superseded), and which proposal the user last confirmed: its requirements are the only "
    "ones checks will read."
)


class RequirementDraft(BaseModel):
    target: Target
    quote: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]


class BriefCreated(BaseModel):
    brief_id: str


class RequirementRow(BaseModel):
    requirement: Requirement
    plain: str
    check: str | None
    status: Literal["proposed", "confirmed"]


class ProposalView(BaseModel):
    brief_id: str
    proposal: int
    status: Status
    requirements: list[RequirementRow]


class BriefView(BaseModel):
    brief_id: str
    text: str
    proposals: list[ProposalView]
    confirmed_proposal: int | None


class ConfirmedAnswer(BaseModel):
    outcome: Literal["confirmed"] = "confirmed"
    requirements: list[RequirementRow]


class DeclinedAnswer(BaseModel):
    outcome: Literal["declined"] = "declined"
    note: str


class PendingAnswer(BaseModel):
    outcome: Literal["pending"] = "pending"
    message: str = (
        "The confirmation page is open in the user's browser and has no answer yet. Tell the "
        "user it is waiting for them. Call confirm_requirements again once they say they "
        "answered, or to open the page again. Build no geometry for this brief until it returns "
        "confirmed."
    )


class ConfirmResult(BaseModel):
    brief_id: str
    proposal: int
    answer: Annotated[
        ConfirmedAnswer | DeclinedAnswer | PendingAnswer, Field(discriminator="outcome")
    ]


def _view(state: BriefState, proposed: ProposalState) -> ProposalView:
    confirmed = state.confirmed
    in_force = {r.id for r in confirmed.proposal.requirements} if confirmed else set[str]()
    return ProposalView(
        brief_id=state.brief.id,
        proposal=proposed.proposal.number,
        status=proposed.status,
        requirements=[
            RequirementRow(
                requirement=r,
                plain=describe(r),
                check=deciding_check(r.target.kind),
                status="confirmed" if r.id in in_force else "proposed",
            )
            for r in proposed.proposal.requirements
        ],
    )


@contextmanager
def _agent_facing() -> Iterator[None]:
    try:
        yield
    except BriefRefused as error:
        raise ToolError(f"{type(error).__name__}: {error}") from error
    except BriefStoreUnusable as error:
        raise ToolError(str(error)) from error


def brief_tools(root: Path, desk: Desk) -> list[Tool]:
    def create_brief(
        text: Annotated[str, Field(min_length=1, max_length=MAX_BRIEF_CHARS)],
    ) -> BriefCreated:
        with _agent_facing():
            return BriefCreated(brief_id=store.create_brief(root, text).id)

    def propose_requirements(
        brief_id: str,
        requirements: Annotated[
            list[RequirementDraft], Field(min_length=1, max_length=MAX_REQUIREMENTS)
        ],
    ) -> ProposalView:
        drafts = [store.Draft(target=r.target, quote=r.quote) for r in requirements]
        with _agent_facing():
            proposed = store.propose(root, brief_id, drafts)
            return _view(store.read_state(root, brief_id), proposed)

    async def confirm_requirements(brief_id: str) -> ConfirmResult:
        with _agent_facing():
            after = await desk.confirm(brief_id)
            state = store.read_state(root, brief_id)
        decision = after.decision
        answer: ConfirmedAnswer | DeclinedAnswer | PendingAnswer
        if decision is None:
            answer = PendingAnswer()
        elif isinstance(decision.answer, Declined):
            answer = DeclinedAnswer(note=decision.answer.note)
        else:
            answer = ConfirmedAnswer(requirements=_view(state, after).requirements)
        return ConfirmResult(brief_id=state.brief.id, proposal=after.proposal.number, answer=answer)

    def list_requirements(brief_id: str) -> BriefView:
        with _agent_facing():
            state = store.read_state(root, brief_id)
        confirmed = state.confirmed
        return BriefView(
            brief_id=state.brief.id,
            text=state.brief.text,
            proposals=[_view(state, p) for p in state.proposals],
            confirmed_proposal=confirmed.proposal.number if confirmed else None,
        )

    return [
        Tool.from_function(create_brief, description=CREATE_BRIEF),
        Tool.from_function(propose_requirements, description=PROPOSE_REQUIREMENTS),
        Tool.from_function(confirm_requirements, description=CONFIRM_REQUIREMENTS),
        Tool.from_function(list_requirements, description=LIST_REQUIREMENTS),
    ]
