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
from typing import Final

from mcp import Client
from mcp.server import MCPServer

from cad.accounts.principal import AgentToken, PersonSession
from cad.briefs import store as briefs
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
from cad.operations.guidance import (
    CHAT_MODE_NOTES,
    CHAT_ON_THE_PAGE,
    CHAT_OPEN_PROJECT,
    INSTRUCTIONS,
)
from cad.operations.model import Tenant
from cad.operations.registry import OPERATIONS
from cad.operations.tenants import Tenants, bind
from cad.operations.tools import tools
from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId

CLIENT_ID: Final = "cad-chat"
MAX_STEPS: Final = 100
MAX_RESULT_CHARS: Final = 40_000
FIRST_WORDS: Final = 120
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
        return bind(tenants.of(token.account), token.conversation)

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
    parts = [INSTRUCTIONS, CHAT_MODE_NOTES[tenant.mode or Mode.PLAN], CHAT_ON_THE_PAGE]
    if tenant.conversation is not None:
        held = store.read(tenant.conversations, tenant.conversation)
        if held.project_id is not None:
            parts.append(_open_project(tenant, ProjectId(held.project_id)))
    return "\n\n".join(parts)


def _open_project(tenant: Tenant, project: ProjectId) -> str:
    lines = [
        f"- {brief_id}: {_first_words(briefs.read_brief(tenant.roots, brief_id).text)}"
        for brief_id in project_briefs(tenant.roots, project)
    ]
    return CHAT_OPEN_PROJECT.format(project_id=project, briefs="\n".join(lines) or "- none yet")


def _first_words(text: str) -> str:
    words = " ".join(text.split())
    return words if len(words) <= FIRST_WORDS else f"{words[:FIRST_WORDS].rstrip()}…"


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
