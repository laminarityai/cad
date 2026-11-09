from typing import Annotated, Final, Literal

from mcp.server.mcpserver.tools import Tool
from pydantic import BaseModel, Field

from cad.briefs import store
from cad.briefs.model import Declined
from cad.briefs.store import BriefState, Status
from cad.confirmations.ballot import Desk
from cad.context_parts.model import Outcome
from cad.context_parts.store import Stored, newest_parts
from cad.projects.membership import project_briefs
from cad.projects.model import PROJECT_ID, PROJECT_ID_CHARS, UnknownProject, parse_project_id
from cad.records.roots import Roots
from cad.server.refusals import agent_facing

ASK_TO_CONFIRM = (
    "Ask the user to confirm everything waiting on them in a project, on one page that opens in "
    "their browser: the newest proposed requirements of every brief in the project and every "
    "context part proposed with propose_context_part. One click confirms or declines the whole "
    "page. Waits up to about 20 seconds, then returns each brief's newest proposal and each "
    "context part as waiting, confirmed, or declined with the user's note. waiting is not an "
    "answer. Calling again opens the same page again while nothing changed; it never confirms "
    "anything."
)
NEXT: Final = {
    "pending": (
        "The confirmation page is open in the user's browser and has no answer yet. Tell the "
        "user it is waiting for them. Call ask_to_confirm again once they say they answered, or "
        "to open the page again. Build no geometry for a brief until it is confirmed."
    ),
    "declined": (
        "The user declined an item. Read their note, revise with propose_requirements or "
        "propose_context_part, and call ask_to_confirm again."
    ),
    "answered": (
        "The user confirmed, and may have changed numbers on the page. Read what they confirmed "
        "with list_requirements, build with build_variant, and pass the brief_id to "
        "score_variant."
    ),
    "nothing_to_confirm": (
        "Nothing in this project waits on the user. Propose requirements with "
        "propose_requirements, or a context part with propose_context_part, first."
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


class AskResult(BaseModel):
    project_id: str
    status: Literal["nothing_to_confirm", "pending", "answered"]
    items: list[RequirementsItem | ContextPartItem]
    next: str


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


def _part_item(part: Stored) -> ContextPartItem:
    facts = part.record.facts
    return ContextPartItem(
        part_id=part.record.id,
        name=part.record.name,
        outcome=part.outcome,
        box_min=facts.box_min,
        box_max=facts.box_max,
        note=part.note,
    )


def confirmation_tools(roots: Roots, desk: Desk) -> list[Tool]:
    async def ask_to_confirm(
        project_id: Annotated[str, Field(max_length=PROJECT_ID_CHARS, pattern=PROJECT_ID.pattern)],
    ) -> AskResult:
        with agent_facing():
            project = parse_project_id(project_id)
            briefs = project_briefs(roots, project)
            if not briefs:
                raise UnknownProject(f"no project {project} is stored; create_brief starts one")
            await desk.ask(project)
            found = [_item(store.read_state(roots, brief_id)) for brief_id in briefs]
            parts = [_part_item(part) for part in newest_parts(roots.projects, project)]
        items: list[RequirementsItem | ContextPartItem] = [
            item for item in found if item is not None
        ]
        items.extend(parts)
        outcomes = {item.outcome for item in items}
        status: Literal["nothing_to_confirm", "pending", "answered"] = (
            "pending" if "waiting" in outcomes else "answered" if items else "nothing_to_confirm"
        )
        advice = [status] if status != "answered" or "declined" not in outcomes else []
        if "declined" in outcomes:
            advice.append("declined")
        return AskResult(
            project_id=project,
            status=status,
            items=items,
            next=" ".join(NEXT[one] for one in advice),
        )

    return [Tool.from_function(ask_to_confirm, description=ASK_TO_CONFIRM)]
