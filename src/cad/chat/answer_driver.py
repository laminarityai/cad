"""What the chat does when the person answers the confirmation page.

The transcript says what the conversation has been told. An `ask_to_confirm` result carries
`answers_recorded`, the number of answers in the project's ledger when the tool read it, and a
`DriverSaid` with `answered` says the server told the agent about answers up to `through`. So
a conversation whose last such event is a pending result waits on any answer past its count,
and appending the delivery is what ends the wait: it can never be delivered twice.

Plan ends on an edge, not a level. The conversation moves to Design only in the step that tells
it about a new answer that confirms a requirements item, so a person who switches back to Plan
stays there until they confirm again.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import ValidationError

from cad.chat.log import Answered, DriverSaid, Event, ToolCalled, ToolReturned
from cad.chat.model import ToolResult, ToolUse
from cad.confirmations.answers import Ledger, PageAnswer, read_ledger
from cad.conversations import store
from cad.operations.confirmation import AskResult
from cad.operations.model import Tenant
from cad.projects.model import ProjectId

ASK: Final = "ask_to_confirm"
ANSWERED: Final = (
    "The person answered the confirmation page of project {project}: they confirmed {confirmed} "
    "and declined {declined}.{notes} Call ask_to_confirm with project_id {project} to read each "
    "item's outcome, and list_requirements for what they confirmed. Then carry on without "
    "waiting for them: build and score what they confirmed, and revise what they declined."
)


@dataclass(frozen=True, slots=True)
class Waiting:
    project: ProjectId
    through: int


@dataclass(frozen=True, slots=True)
class Delivery:
    event: DriverSaid
    ends_plan: bool


def waiting_on(events: Sequence[Event]) -> Waiting | None:
    """The last `ask_to_confirm` result or delivery decides. Only a pending result waits. An
    error result tells nothing, and a result cut too long to read counts as not pending."""
    calls = _ask_calls(events)
    found: Waiting | None = None
    for event in events:
        if isinstance(event, DriverSaid) and event.answered is not None:
            found = None
        elif isinstance(event, ToolReturned) and event.call_id in calls and not event.is_error:
            result = _parsed(event.text)
            found = None
            if result is not None and result.status == "pending":
                found = Waiting(ProjectId(result.project_id), result.answers_recorded)
    return found


def told_through(events: Sequence[Event], project: ProjectId) -> int:
    calls = _ask_calls(events)
    told = 0
    for event in events:
        if isinstance(event, DriverSaid) and event.answered is not None:
            if event.answered.project_id == project:
                told = max(told, event.answered.through)
            continue
        result = _asked(event, calls)
        if result is not None and result.project_id == project:
            told = max(told, result.answers_recorded)
    return told


def delivery(waiting: Waiting, ledger: Ledger) -> Delivery | None:
    """One event for every answer past what the conversation was told, or None."""
    through = len(ledger.answers)
    new = [page for _, page in ledger.answers[waiting.through : through]]
    if not new:
        return None
    verdicts = [one.verdict for page in new for one in page.answers]
    notes = "".join(f' Their note: "{page.note}".' for page in new if page.note)
    text = ANSWERED.format(
        project=waiting.project,
        confirmed=verdicts.count("confirmed"),
        declined=verdicts.count("declined"),
        notes=notes,
    )
    event = DriverSaid(text=text, answered=Answered(project_id=waiting.project, through=through))
    return Delivery(event, confirms_requirements(new))


def confirms_requirements(pages: Sequence[PageAnswer]) -> bool:
    return any(
        one.item.kind == "requirements" and one.verdict == "confirmed"
        for page in pages
        for one in page.answers
    )


def settle(tenant: Tenant, events: Sequence[Event], call: ToolUse, result: ToolResult) -> None:
    """The agent's own `ask_to_confirm` saw new answers. Runs before its result is appended, so
    `events` still holds what the conversation was told before it."""
    if call.name != ASK or result.is_error or tenant.conversation is None:
        return
    asked = _parsed(result.text)
    if asked is None or asked.status == "pending":
        return
    project = ProjectId(asked.project_id)
    before = told_through(events, project)
    if asked.answers_recorded <= before:
        return
    ledger = read_ledger(tenant.roots.projects, project)
    new = [page for _, page in ledger.answers[before : asked.answers_recorded]]
    if confirms_requirements(new):
        store.confirmed(tenant.conversations, tenant.conversation)


def _ask_calls(events: Sequence[Event]) -> frozenset[str]:
    return frozenset(
        one.call_id for one in events if isinstance(one, ToolCalled) and one.name == ASK
    )


def _asked(event: Event, calls: frozenset[str]) -> AskResult | None:
    if not isinstance(event, ToolReturned) or event.call_id not in calls or event.is_error:
        return None
    return _parsed(event.text)


def _parsed(text: str) -> AskResult | None:
    try:
        return AskResult.model_validate_json(text)
    except ValidationError:
        return None
