"""One agent turn, run in the server for the person's message.

The turn is a client of the same MCP tools as any outside client (ADR-0002). It opens an in-memory
`mcp.Client` on a server built from the registry, so the agent's tool list is the registry's
AGENT list and nothing else. The server gets an `AgentToken` built from the person's verified
session, naming only the conversation. At each tool call it reads the conversation's mode and Auto
run from the account's store, so a switch of mode or a press of Stop reaches the next call, even
in the middle of a turn. The token never leaves this process.
"""

import json
import logging
import secrets
from collections.abc import Mapping
from typing import Final

from mcp import Client
from mcp.server import MCPServer

from cad.accounts.principal import AgentToken, PersonSession
from cad.accounts.tenants import Tenants
from cad.chat import answer_driver
from cad.chat.auto_driver import AutoDriver
from cad.chat.log import (
    AgentSaid,
    Channel,
    DriverSaid,
    ToolCalled,
    ToolReturned,
    TurnEnded,
    TurnFailed,
    messages_of,
)
from cad.chat.model import Message, Model, ModelUnavailable, Text, ToolResult, ToolSpec, ToolUse
from cad.conversations import store
from cad.conversations.model import ConversationId, Mode
from cad.operations.guidance import INSTRUCTIONS
from cad.operations.model import Tenant
from cad.operations.registry import OPERATIONS
from cad.operations.tools import tools

CLIENT_ID: Final = "cad-chat"
MAX_STEPS: Final = 100
MAX_RESULT_CHARS: Final = 40_000
MODE_NOTES: Final[Mapping[Mode, str]] = {
    Mode.PLAN: (
        "This conversation is in Plan mode. Turn the person's words into requirements and ask "
        "them to confirm. The server refuses build_variant in Plan mode. When the person "
        "confirms, the server moves the conversation to Design mode and starts your next turn "
        "by itself. After ask_to_confirm returns pending, tell the person to answer on the page "
        "and end your message."
    ),
    Mode.DESIGN: (
        "This conversation is in Design mode. Build and revise variants when the person asks, "
        "and report only what the checks returned. You act when the person writes or answers the "
        "confirmation page."
    ),
    Mode.AUTO: (
        "This conversation is in Auto mode. Call auto_start with the brief_id of a brief whose "
        "requirements the person confirmed, then call auto_revise with new build123d code for "
        "the failing requirements until the run stops. Call auto_ask when you are stuck or the "
        "person must decide. The server decides when the run stops, and the person can press "
        "Stop at any time. Never call set_mode: only the person switches modes."
    ),
}

OPEN_BRIEF: Final = (
    "The person started this conversation on project {project_id}, brief {brief_id}, which "
    "their page shows. A slot they name is a slot of this brief's variant set: call variant_set "
    "with this project_id and brief_id for each slot's variant_id and revision, and variant_code "
    "for the code a variant was built from. To change a slot, edit that code and build it with "
    "build_variant, this brief_id and that slot. A change to a slot stays in this brief: a "
    "revision when no number is stated, and a new proposal on this brief when one is. Then "
    "score the new variant with score_variant and this brief_id: only that runs the checks, "
    "and the person's scorecard waits on it. The "
    "material is the one the brief's made_of requirement confirms (list_requirements shows it). "
    "When none does, choose one for each variant and pass it to build_variant as material_key "
    "with a one-line material_reason: omit both to keep the slot's choice. When the person asks "
    "for a particular material, propose it as a made_of requirement for them to confirm. Never "
    "ask the person to choose a material. Do not "
    "ask the person for code, a brief, a material or an id that these tools return."
)

ON_THE_PAGE: Final = (
    "The person reads this chat beside their project page. The page shows every brief, every "
    "variant in its own tab with its 3D view, its scorecard as it runs, and each slot's earlier "
    "revisions, and it updates by itself after each build and score. So never restate a "
    "scorecard, a check result, a measurement, a list of variants or an id in your reply, and "
    "never write a table. After you build or score, reply in one or two short sentences that "
    "say what changed and point at the page, for example: Built 3 lid options, see the tabs. "
    "When the person must choose, ask one short question. When you need the person to confirm, "
    "call ask_to_confirm: the page draws the items in this chat with a Confirm button, so do "
    "not list them yourself. Never ask the person for an id, a mode or a material."
)

_LOG = logging.getLogger(__name__)


def agent_token(person: PersonSession, cid: ConversationId) -> AgentToken:
    return AgentToken(
        account=person.account,
        token_id=f"turn_{secrets.token_hex(8)}",
        client_id=CLIENT_ID,
        conversation=cid,
    )


async def run_turn(model: Model, tenants: Tenants, token: AgentToken, channel: Channel) -> None:
    """Run until the model has nothing more to call or the run stops. Never raises: whatever goes
    wrong becomes a `TurnFailed` the person reads, and the turn always ends with `TurnEnded`."""
    try:
        await _converse(model, tenants, token, channel)
    except Exception:
        _LOG.exception("chat turn %s failed", token.token_id)
        channel.append(TurnFailed(message="the agent failed; the server log holds the cause"))
    finally:
        channel.append(TurnEnded())
        channel.running = False


async def _converse(model: Model, tenants: Tenants, token: AgentToken, channel: Channel) -> None:
    def tenant_of() -> Tenant:
        return store.bind(tenants.of(token.account), token.conversation)

    server = MCPServer("cad", instructions=INSTRUCTIONS, tools=tools(tenant_of, OPERATIONS))
    async with Client(server) as client:
        specs = [
            ToolSpec(
                name=one.name, description=one.description or "", input_schema=one.input_schema
            )
            for one in (await client.list_tools()).tools
        ]
        events = channel.events()
        messages = messages_of(events)
        driver = AutoDriver.resume(tenant_of(), events)
        missed = driver.ending()
        if missed is not None:
            channel.append(missed)
            if isinstance(missed, TurnFailed):
                return
        for _ in range(MAX_STEPS):
            try:
                reply = await model.reply(_system(tenant_of()), messages, specs)
            except ModelUnavailable as unavailable:
                channel.append(TurnFailed(message=str(unavailable)))
                return
            messages.append(reply)
            _say(channel, reply)
            calls = reply.calls
            if calls:
                results: list[ToolResult] = []
                for call in calls:
                    result = await _call(client, call)
                    answer_driver.settle(tenant_of(), channel.events(), call, result)
                    channel.append(
                        ToolReturned(call_id=call.id, text=result.text, is_error=result.is_error)
                    )
                    driver.observe(call, result)
                    results.append(result)
                messages.append(Message(role="user", blocks=tuple(results)))
            ending = driver.ending()
            if ending is not None:
                channel.append(ending)
                return
            if not calls:
                nudge = driver.nudge()
                if nudge is None:
                    return
                channel.append(DriverSaid(text=nudge))
                messages.append(Message(role="user", blocks=(Text(text=nudge),)))
        channel.append(
            TurnFailed(message=f"the turn used its {MAX_STEPS} steps; send a message to continue")
        )


def _system(tenant: Tenant) -> str:
    parts = [INSTRUCTIONS, MODE_NOTES[tenant.mode or Mode.PLAN], ON_THE_PAGE]
    if tenant.conversation is not None:
        held = store.read(tenant.conversations, tenant.conversation)
        if held.project_id is not None and held.brief_id is not None:
            parts.append(OPEN_BRIEF.format(project_id=held.project_id, brief_id=held.brief_id))
    return "\n\n".join(parts)


def _say(channel: Channel, reply: Message) -> None:
    for block in reply.blocks:
        if isinstance(block, Text):
            channel.append(AgentSaid(text=block.text))
        elif isinstance(block, ToolUse):
            channel.append(ToolCalled(call_id=block.id, name=block.name, input=block.input))


async def _call(client: Client, call: ToolUse) -> ToolResult:
    result = await client.call_tool(call.name, call.input)
    if result.structured_content is not None:
        text = json.dumps(result.structured_content, separators=(",", ":"))
    else:
        text = "\n".join(one.text for one in result.content if one.type == "text")
    return ToolResult(call_id=call.id, text=_cut(text), is_error=result.is_error)


def _cut(text: str) -> str:
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return f"{text[:MAX_RESULT_CHARS]}\n[cut: {len(text) - MAX_RESULT_CHARS} more characters]"
