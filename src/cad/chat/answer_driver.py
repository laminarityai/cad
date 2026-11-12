"""What the chat does when the person answers the confirmation page.

The transcript says what the conversation has been told. An `ask_to_confirm` result carries
`answers_recorded`, the number of answers in the project's ledger when the tool read it, and a
`DriverSaid` with `answered` says the server told the agent about answers up to `through`. So
a conversation whose last such event is a pending result waits on any answer past its count,
and appending the delivery is what ends the wait: it can never be delivered twice.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import ValidationError

from cad.chat.log import Answered, DriverSaid, Event, ToolCalled, ToolReturned
from cad.confirmations.answers import Ledger
from cad.operations.confirmation import AskResult
from cad.projects.model import ProjectId

ASK: Final = "ask_to_confirm"
ANSWERED: Final = (
    "The person answered the confirmation page of project {project}: they confirmed {confirmed} "
    "and declined {declined}.{notes} Call ask_to_confirm with project_id {project} to read each "
    "item's outcome, and list_requirements for what they confirmed. Nothing you built is gone, "
    "and the scorecards now judge it against what they confirmed with no rebuild. Then carry on "
    "without waiting for them. Score again to read the verdicts. For what they declined, read "
    "their note and propose again, file the value as an assumption, or drop it. When nothing "
    "waits for the person and an option fails a requirement they confirmed that a check "
    "decides, call auto_start with its brief_id, then auto_revise until the run stops."
)


@dataclass(frozen=True, slots=True)
class Waiting:
    project: ProjectId
    through: int


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


def delivery(waiting: Waiting, ledger: Ledger) -> DriverSaid | None:
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
    return DriverSaid(text=text, answered=Answered(project_id=waiting.project, through=through))


def _ask_calls(events: Sequence[Event]) -> frozenset[str]:
    return frozenset(
        one.call_id for one in events if isinstance(one, ToolCalled) and one.name == ASK
    )


def _parsed(text: str) -> AskResult | None:
    try:
        return AskResult.model_validate_json(text)
    except ValidationError:
        return None
