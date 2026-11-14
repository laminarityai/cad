from datetime import UTC, datetime
from typing import Annotated, Final, Literal

import anyio.to_thread
from pydantic import BaseModel, Field

from cad.accounts.principal import PersonSession
from cad.agent_checks.store import StoredCheck
from cad.briefs import store
from cad.briefs.model import Declined
from cad.briefs.store import BriefState, Status
from cad.confirmations import agent_checks, page, snapshot
from cad.confirmations.answers import read_ledger
from cad.confirmations.items import Refused, pending
from cad.confirmations.page import AlreadyAnswered, Changed, Recorded
from cad.confirmations.registry import kinds
from cad.context_parts.ids import ContextPartId
from cad.context_parts.model import UPDATE_PART, NewerRevision, Outcome
from cad.context_parts.store import Stored, newer_revisions, newest_parts
from cad.operations.model import Audience, Input, Tenant, operation
from cad.projects.membership import project_briefs
from cad.projects.model import (
    PROJECT_ID,
    PROJECT_ID_CHARS,
    ProjectId,
    UnknownProject,
    parse_project_id,
)
from cad.records.roots import Roots

ASK_TO_CONFIRM = (
    "Ask the user to confirm everything waiting on them in a project, on the project's one "
    "confirmation page in the web app: the newest proposed requirements of every brief in the "
    "project, every context part proposed with propose_context_part, and every agent-written "
    "check a proposed requirement names. One click there confirms or declines the whole page, "
    "and only the signed-in user can press it. A client that can open a page for the user is "
    "asked to open it. Waits up to about 20 seconds, then returns each brief's newest proposal, "
    "each context part and each agent-written check as waiting, confirmed, or declined with "
    "the user's note. A confirmed agent_check is one the person approved. waiting is not an "
    "answer. This tool never confirms anything. A confirmed context part whose slot now shows a "
    "newer revision has newer_revision: " + UPDATE_PART
)
ANSWER_PAGE = "Record the signed-in person's answer to a project's confirmation page."
NEXT: Final = {
    "pending": (
        "The confirmation is waiting in the web app and has no answer yet. Tell the user to "
        "answer it there, on the project's confirmation page. In the web app's chat their answer "
        "reaches you by itself, so end your message and do not ask them to tell you. Any other "
        "client calls ask_to_confirm again after they answer. What you built stays, and the "
        "scorecards show each target that waits as waiting on the person, with its measure."
    ),
    "declined": (
        "The user declined an item. Nothing you built is removed. Read their note, then revise "
        "with propose_requirements or propose_context_part and call ask_to_confirm again, or "
        "file the value as an assumption, or drop it."
    ),
    "answered": (
        "The user confirmed, and may have changed numbers on the page. Read what they confirmed "
        "with list_requirements, then call score_variant with the brief_id for each option. "
        "The stored check results are judged against what they confirmed with no rebuild. "
        "Revise only an option that fails a confirmed target."
    ),
    "nothing_to_confirm": (
        "Nothing in this project waits on the user. A brief that states no number needs no "
        "confirmation. When the user did state one, propose it with propose_requirements, or "
        "a context part with propose_context_part, first."
    ),
}


class RequirementsItem(BaseModel):
    kind: Literal["requirements"] = "requirements"
    brief_id: str
    proposal: int
    outcome: Outcome
    note: str = ""


class ContextPartItem(BaseModel):
    kind: Literal["context_part"] = "context_part"
    part_id: str
    name: str
    outcome: Outcome
    box_min: tuple[float, float, float]
    box_max: tuple[float, float, float]
    note: str = ""
    newer_revision: NewerRevision | None = None


class AgentCheckItem(BaseModel):
    """An agent-written check a requirement names. Confirmed means the person approved it."""

    kind: Literal["agent_check"] = "agent_check"
    check_sha256: str
    title: str
    brief_id: str
    outcome: Outcome
    note: str = ""


type Item = RequirementsItem | ContextPartItem | AgentCheckItem


class AskResult(BaseModel):
    project_id: str
    status: Literal["nothing_to_confirm", "pending", "answered"]
    items: list[Item]
    next: str
    answers_recorded: int = Field(
        description="How many answers the project's page has recorded when the items were read."
    )


def _item(state: BriefState) -> RequirementsItem | None:
    latest = state.latest
    if latest is None:
        return None
    answer = latest.answered.answer if latest.answered else None
    outcome: Outcome = "waiting"
    if latest.status is Status.CONFIRMED:
        outcome = "confirmed"
    elif latest.status is Status.DECLINED:
        outcome = "declined"
    return RequirementsItem(
        brief_id=state.brief.id,
        proposal=latest.proposal.number,
        outcome=outcome,
        note=answer.note if isinstance(answer, Declined) else "",
    )


def _part_item(part: Stored, newer: dict[ContextPartId, NewerRevision]) -> ContextPartItem:
    facts = part.record.facts
    return ContextPartItem(
        part_id=part.record.id,
        name=part.record.name,
        outcome=part.outcome,
        box_min=facts.box_min,
        box_max=facts.box_max,
        note=part.note,
        newer_revision=newer.get(part.record.id),
    )


def _check_item(roots: Roots, project: ProjectId, stored: StoredCheck) -> AgentCheckItem:
    return AgentCheckItem(
        check_sha256=stored.sha256,
        title=stored.check.title,
        brief_id=stored.check.brief_id,
        outcome=agent_checks.outcome(roots, project, stored),
        note=agent_checks.note(roots, project, stored),
    )


class AskToConfirmInput(Input):
    project_id: Annotated[str, Field(max_length=PROJECT_ID_CHARS, pattern=PROJECT_ID.pattern)]


def _known(tenant: Tenant, arguments: AskToConfirmInput) -> tuple[ProjectId, tuple[str, ...]]:
    project = parse_project_id(arguments.project_id)
    briefs = project_briefs(tenant.roots, project)
    if not briefs:
        raise UnknownProject(f"no project {project} is stored; create_brief starts one")
    return project, briefs


def confirm_page(tenant: Tenant, arguments: AskToConfirmInput) -> str | None:
    project, _ = _known(tenant, arguments)
    if tenant.door.page_url is None or not pending(kinds(tenant.roots), project):
        return None
    return tenant.door.page_url(project)


async def ask_to_confirm(tenant: Tenant, arguments: AskToConfirmInput) -> AskResult:
    project, briefs = _known(tenant, arguments)
    every = kinds(tenant.roots)
    waiting = pending(every, project)
    if waiting:
        door = tenant.door
        if door.open_page is not None:
            await anyio.to_thread.run_sync(door.open_page, tenant.account, project)
        await anyio.to_thread.run_sync(
            tenant.bell.wait,
            lambda: pending(every, project) != waiting,
            door.wait_seconds,
            abandon_on_cancel=True,
        )
    # Counted before the items while one waits, so it never counts an answer they do not show.
    recorded = len(read_ledger(tenant.roots.projects, project).answers)
    found = [_item(store.read_state(tenant.roots, brief_id)) for brief_id in briefs]
    items: list[Item] = [item for item in found if item is not None]
    newer = newer_revisions(tenant.roots.projects, tenant.variants, project)
    items.extend(_part_item(part, newer) for part in newest_parts(tenant.roots.projects, project))
    items.extend(
        _check_item(tenant.roots, project, one) for one in agent_checks.named(tenant.roots, project)
    )
    outcomes = {item.outcome for item in items}
    status: Literal["nothing_to_confirm", "pending", "answered"] = (
        "pending" if "waiting" in outcomes else "answered" if items else "nothing_to_confirm"
    )
    if status != "pending":
        # Nothing waits, so no answer can follow the items: count one that landed before them.
        recorded = len(read_ledger(tenant.roots.projects, project).answers)
    advice = [status] if status != "answered" or "declined" not in outcomes else []
    if "declined" in outcomes:
        advice.append("declined")
    return AskResult(
        project_id=project,
        status=status,
        items=items,
        next=" ".join(NEXT[one] for one in advice),
        answers_recorded=recorded,
    )


FORBIDDEN: Final = "This page is not yours to answer. Open it again from the web app."
CHANGED: Final = (
    "The agent added or changed something since this page opened. Nothing was recorded. "
    "Open the page again to see what waits on you."
)
NOT_A_FORM: Final = "The answer was not sent as a form."


class AnswerPageInput(Input):
    project_id: Annotated[str, Field(max_length=PROJECT_ID_CHARS, pattern=PROJECT_ID.pattern)]
    person: PersonSession
    form: bytes


class PageReply(BaseModel):
    outcome: Literal["recorded", "already_answered", "changed", "refused", "forbidden"]
    said: tuple[str, ...]


def answer_page(tenant: Tenant, arguments: AnswerPageInput) -> PageReply:
    project = parse_project_id(arguments.project_id)
    person = arguments.person
    sealed = page.sealed_snapshot(arguments.form)
    items = (
        None
        if sealed is None or person.account != tenant.account
        else snapshot.unseal(tenant.roots.projects, person, project, sealed)
    )
    if not items:
        return PageReply(outcome="forbidden", said=(FORBIDDEN,))
    form = page.parse_form(arguments.form, len(items))
    if form is None:
        return PageReply(outcome="refused", said=(NOT_A_FORM,))
    every = kinds(tenant.roots)
    changes = page.read_edits(every, items, form)
    if isinstance(changes, Refused):
        return PageReply(outcome="refused", said=(changes.message,))
    now = datetime.now(UTC)
    match page.answer_page(tenant.roots, every, project, items, form, person, now):
        case Recorded(confirmed=confirmed, declined=declined):
            said = f"Recorded. You confirmed {confirmed} and declined {declined} on this page."
            return PageReply(outcome="recorded", said=(said, *changes, "Return to the chat."))
        case AlreadyAnswered():
            return PageReply(outcome="already_answered", said=("This page was already answered.",))
        case Changed():
            return PageReply(outcome="changed", said=(CHANGED,))


OPERATIONS: Final = (
    operation(
        name="ask_to_confirm",
        audience=Audience.AGENT,
        description=ASK_TO_CONFIRM,
        input=AskToConfirmInput,
        output=AskResult,
        run=ask_to_confirm,
        page=confirm_page,
    ),
    operation(
        name="answer_page",
        audience=Audience.PAGE,
        description=ANSWER_PAGE,
        input=AnswerPageInput,
        output=PageReply,
        run=answer_page,
    ),
)
