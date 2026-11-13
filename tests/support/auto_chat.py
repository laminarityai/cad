import json
from collections.abc import Sequence
from typing import Any, Final

from cad.accounts.principal import AccountId
from cad.auto.log import read_run
from cad.chat.scripted import Step
from cad.conversations.model import ConversationId
from tests.support.chat import ALICE, Chat, call, step
from tests.support.rows import UNDER_150

RUN: Final = "${auto_start.run_id}"


def confirmed() -> list[Step]:
    return [
        step("Storing the brief.", call("create_brief")),
        step(
            "Proposing requirements.",
            call(
                "propose_requirements",
                brief_id="${create_brief.brief_id}",
                requirements=[UNDER_150],
            ),
        ),
        step(
            "Asking you to confirm.",
            call("ask_to_confirm", project_id="${create_brief.project_id}"),
        ),
        step(
            "Starting the run.",
            call(
                "auto_start",
                brief_id="${create_brief.brief_id}",
                material_key="prusament-pla",
                material_reason="PLA is light and prints easily",
            ),
        ),
    ]


def run_of(chat: Chat, cid: str) -> Any:
    tenant = chat.tenants.of(AccountId(ALICE))
    channel = chat.app.state.chat.channels.of(
        AccountId(ALICE), tenant.conversations, ConversationId(cid)
    )
    events = channel.events()
    started = next(one.call_id for one in events if getattr(one, "name", None) == "auto_start")
    returned = next(one for one in events if one.kind == "tool_result" and one.call_id == started)
    return read_run(tenant.roots, json.loads(returned.text)["run_id"])


def kinds(events: Sequence[Any]) -> list[str]:
    return [one["kind"] for one in events]
