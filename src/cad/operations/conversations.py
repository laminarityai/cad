from typing import Final

from pydantic import BaseModel

from cad.auto.model import AutoRun, Running
from cad.briefs.store import BriefRefused
from cad.checks.lanes import LANES
from cad.conversations import store
from cad.conversations.model import (
    ConversationId,
    ConversationRefused,
    NotAConversation,
    conversation_id,
)
from cad.errors import Unavailable
from cad.operations.model import Audience, Input, Tenant, operation
from cad.sandbox import image
from cad.variant_sets.model import SetRefused
from cad.variant_sets.store import builds, members, set_key

CONVERSATION = (
    "One conversation of the signed-in person: the project and brief it was started on, its "
    "running Auto run, the run whose stop holds it until the person writes or answers, and the "
    "latest Auto run it started, running or stopped with its reason, and whether that run's "
    "checks are still queued or running. The web app "
    "reads it on load, when the tab comes back into view, after each turn and every few seconds "
    "while it is open, so a Stop pressed in another tab shows here."
)


class ConversationInput(Input):
    conversation_id: str


class ConversationState(BaseModel):
    conversation_id: str
    auto_run: str | None
    stopped_run: str | None


class ConversationView(ConversationState):
    project_id: str | None
    brief_id: str | None
    run: AutoRun | None
    checks_settling: bool


def _parsed(raw: str) -> ConversationId:
    try:
        return conversation_id(raw)
    except NotAConversation as error:
        raise ConversationRefused(str(error)) from error


def conversation(tenant: Tenant, arguments: ConversationInput) -> ConversationView:
    cid = _parsed(arguments.conversation_id)
    held = store.read(tenant.conversations, cid)
    run = store.last_run(tenant.roots, held)
    return ConversationView(
        conversation_id=cid,
        auto_run=held.auto_run,
        stopped_run=held.stopped_run,
        project_id=held.project_id,
        brief_id=held.brief_id,
        run=run,
        checks_settling=_settling(tenant, run),
    )


def _settling(tenant: Tenant, run: AutoRun | None) -> bool:
    """A running Auto run whose variants still have checks queued or running, after the turn that
    started them ended. The page then says so instead of that nothing is working."""
    if run is None or not isinstance(run.state, Running):
        return False
    try:
        tag = image.image_tag(image.BUILD)
        key = set_key(tenant.roots, run.state.start.brief_id)
        ids = {
            one
            for member in members(tenant.roots.projects, key)
            for one in builds(tenant.variants, member.latest, tag).ids
        }
    except (BriefRefused, SetRefused, Unavailable, OSError):
        return False
    return LANES.busy(tenant.variants, ids)


OPERATIONS: Final = (
    operation(
        name="conversation",
        audience=Audience.PERSON,
        description=CONVERSATION,
        input=ConversationInput,
        output=ConversationView,
        run=conversation,
    ),
)
