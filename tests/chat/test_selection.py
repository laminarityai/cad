import json
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from cad.accounts.principal import AccountId
from cad.chat.log import person_said
from cad.chat.model import Message, Model, Text, ToolSpec
from cad.operations.model import Tenant
from tests.chat.support import ALICE, JSON, Chat, script, step
from tests.selections.support import TOP, confirmed, joined, stored_mesh

pytestmark = pytest.mark.anyio


@dataclass
class Recording:
    inner: Model
    seen: list[Sequence[Message]] = field(default_factory=list[Sequence[Message]])

    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message:
        self.seen.append(tuple(messages))
        return await self.inner.reply(system, messages, tools)


@pytest.fixture
def recording() -> Recording:
    return Recording(script(step("Thicker.")))


@pytest.fixture
def model(recording: Recording) -> Model:
    return recording


async def project_chat(chat: Chat) -> tuple[Tenant, str, str, str]:
    tenant = chat.tenants.of(AccountId(ALICE))
    project = await confirmed(tenant)
    stored_mesh(tenant)
    variant = joined(tenant, project.brief, "result = 1\n")
    made = await chat.client().post(
        "/v1/conversations", headers=JSON, content=json.dumps({"project_id": project.project})
    )
    assert made.status_code == 201, made.text
    return tenant, made.json()["conversation_id"], variant, project.brief


async def send(chat: Chat, cid: str, body: dict[str, object]) -> tuple[int, dict[str, str]]:
    async with chat.client() as client:
        sent = await client.post(
            f"/v1/conversations/{cid}/messages", headers=JSON, content=json.dumps(body)
        )
    return sent.status_code, sent.json()


async def test_a_message_with_a_pick_carries_a_signed_selection_to_the_agent(
    chat: Chat, recording: Recording
) -> None:
    _, cid, variant, brief = await project_chat(chat)
    status, _ = await send(
        chat,
        cid,
        {"text": "make this thicker", "selection": {"variant_id": variant, "faces": [TOP]}},
    )
    await chat.finish()
    async with chat.client() as client:
        events = await chat.events(client, cid)
    assert status == 202
    [said] = [one for one in events if one["kind"] == "user"]
    note = said["selection"]
    assert (note["summary"], note["brief_id"], note["slot"], note["revision"]) == (
        "1 face",
        brief,
        1,
        1,
    )
    told = [
        block.text
        for message in recording.seen[0]
        for block in message.blocks
        if isinstance(block, Text)
    ]
    [block] = told
    assert block.startswith("make this thicker\n\n[server: the person selected 1 face of slot 1")
    assert f"read_selection with {note['selection_id']}" in block
    tenant = chat.tenants.of(AccountId(ALICE))
    assert [text for _, text in person_said(tenant.conversations, cid)] == ["make this thicker"]


async def test_a_pick_the_geometry_does_not_hold_is_refused_and_nothing_is_said(
    chat: Chat,
) -> None:
    _, cid, variant, _ = await project_chat(chat)
    status, body = await send(
        chat, cid, {"text": "this", "selection": {"variant_id": variant, "faces": [99]}}
    )
    async with chat.client() as client:
        events = await chat.events(client, cid)
    assert status == 422
    assert "face 99 is not on this design" in body["error"]
    assert events == []


async def test_a_pick_of_a_variant_not_in_the_project_is_refused(chat: Chat) -> None:
    _, cid, _, _ = await project_chat(chat)
    status, body = await send(
        chat, cid, {"text": "this", "selection": {"variant_id": "0" * 16, "part": True}}
    )
    assert status == 422
    assert "not a design of this project" in body["error"]


async def test_a_pick_in_a_conversation_with_no_project_is_refused(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
    status, body = await send(
        chat, cid, {"text": "this", "selection": {"variant_id": "0" * 16, "part": True}}
    )
    assert status == 422
    assert "no project" in body["error"] or "none" in body["error"]
