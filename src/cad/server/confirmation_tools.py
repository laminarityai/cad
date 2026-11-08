from typing import Annotated, Final, Literal

from mcp.server.mcpserver.tools import Tool
from pydantic import BaseModel, Field

from cad.briefs import store
from cad.briefs.model import Declined
from cad.briefs.store import BriefState, Status
from cad.confirmations.ballot import Desk
from cad.projects.membership import project_briefs
from cad.projects.model import PROJECT_ID, PROJECT_ID_CHARS, UnknownProject, parse_project_id
from cad.records.roots import Roots
from cad.server.refusals import agent_facing

ASK_TO_CONFIRM = (
    "Ask the user to confirm everything waiting on them in a project, on one page that opens in "
    "their browser: the newest proposed requirements of every brief in the project. One click "
    "confirms or declines the whole page. Waits up to about 20 seconds, then returns each "
    "brief's newest proposal as waiting, confirmed, or declined with the user's note. waiting is "
    "not an answer. Calling again opens the same page again while nothing changed; it never "
    "confirms anything."
)
NEXT: Final = {
    "pending": (
        "The confirmation page is open in the user's browser and has no answer yet. Tell the "
        "user it is waiting for them. Call ask_to_confirm again once they say they answered, or "
        "to open the page again. Build no geometry for a brief until it is confirmed."
    ),
    "declined": (
        "The user declined. Read their note, revise with propose_requirements, and call "
        "ask_to_confirm again."
    ),
    "answered": (
        "The user confirmed. Build with build_variant and pass the brief_id to score_variant."
    ),
    "nothing_to_confirm": (
        "Nothing in this project waits on the user. Propose requirements with "
        "propose_requirements first."
    ),
}


class RequirementsItem(BaseModel):
    kind: Literal["requirements"] = "requirements"
    brief_id: str
    proposal: int
    outcome: Literal["waiting", "confirmed", "declined"]
    note: str = ""


class AskResult(BaseModel):
    project_id: str
    status: Literal["nothing_to_confirm", "pending", "answered"]
    items: list[RequirementsItem]
    next: str


def _item(state: BriefState) -> RequirementsItem | None:
    latest = state.latest
    if latest is None:
        return None
    answer = latest.answered.answer if latest.answered else None
    outcome: Literal["waiting", "confirmed", "declined"] = "waiting"
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
        items = [item for item in found if item is not None]
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
