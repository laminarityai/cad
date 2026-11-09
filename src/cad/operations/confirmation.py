from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field

from cad.briefs import store
from cad.briefs.model import Declined
from cad.briefs.store import BriefState, Status
from cad.operations.model import Audience, Input, Tenant, operation
from cad.projects.membership import project_briefs
from cad.projects.model import PROJECT_ID, PROJECT_ID_CHARS, UnknownProject, parse_project_id

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
        "The user confirmed, and may have changed numbers on the page. Read what they confirmed "
        "with list_requirements, build with build_variant, and pass the brief_id to "
        "score_variant."
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


class AskToConfirmInput(Input):
    project_id: Annotated[str, Field(max_length=PROJECT_ID_CHARS, pattern=PROJECT_ID.pattern)]


async def ask_to_confirm(tenant: Tenant, arguments: AskToConfirmInput) -> AskResult:
    project = parse_project_id(arguments.project_id)
    briefs = project_briefs(tenant.roots, project)
    if not briefs:
        raise UnknownProject(f"no project {project} is stored; create_brief starts one")
    await tenant.desk.ask(project)
    found = [_item(store.read_state(tenant.roots, brief_id)) for brief_id in briefs]
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


OPERATIONS: Final = (
    operation(
        name="ask_to_confirm",
        audience=Audience.AGENT,
        description=ASK_TO_CONFIRM,
        input=AskToConfirmInput,
        output=AskResult,
        run=ask_to_confirm,
    ),
)
