import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from urllib.parse import urlencode

import pytest

from cad.accounts.principal import AccountId
from cad.chat.log import Channel, UserSaid, transcript_path
from cad.chat.model import Message, Model, ToolSpec
from cad.conversations import store
from cad.conversations.model import ConversationId, Mode
from cad.operations.briefs import (
    BriefCreated,
    CreateBriefInput,
    ListRequirementsInput,
    ProposeRequirementsInput,
    RequirementDraft,
    create_brief,
    list_requirements,
    propose_requirements,
)
from tests.chat.support import ALICE, BOB, JSON, TEXT, UNDER_150, Chat, script, step

pytestmark = pytest.mark.anyio


@dataclass
class Recording:
    inner: Model
    systems: list[str] = field(default_factory=list[str])

    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message:
        self.systems.append(system)
        return await self.inner.reply(system, messages, tools)


@pytest.fixture
def recording() -> Recording:
    return Recording(script(step("Looking.")))


@pytest.fixture
def model(recording: Recording) -> Model:
    return recording


def brief(chat: Chat, account: str = ALICE) -> BriefCreated:
    return create_brief(chat.tenants.of(AccountId(account)), CreateBriefInput(text=TEXT))


def proposed(chat: Chat, brief_id: str) -> None:
    drafts = [RequirementDraft.model_validate(UNDER_150)]
    tenant = chat.tenants.of(AccountId(ALICE))
    propose_requirements(tenant, ProposeRequirementsInput(brief_id=brief_id, requirements=drafts))


async def test_the_project_chat_names_the_project_and_its_briefs_to_the_agent(
    chat: Chat, recording: Recording
) -> None:
    made = brief(chat)
    body = json.dumps({"project_id": made.project_id, "brief_id": made.brief_id})
    async with chat.client() as client:
        started = await client.post("/v1/conversations", headers=JSON, content=body)
        cid = started.json()["conversation_id"]
        await chat.say(client, cid, "make the side walls of slot 1 thicker")
        await chat.finish()
        read = await client.get(f"/v1/conversations/{cid}")
    assert started.status_code == 201, started.text
    assert read.json() == {
        "conversation_id": cid,
        "mode": "plan",
        "auto_run": None,
        "project_id": made.project_id,
        "brief_id": made.brief_id,
        "run": None,
    }
    system = recording.systems[0]
    assert f"chat of project {made.project_id}" in system
    assert f"- {made.brief_id}: {TEXT}" in system
    assert all(tool in system for tool in ("variant_set", "variant_code", "score_variant"))


async def test_a_conversation_without_a_project_names_none(
    chat: Chat, recording: Recording
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "hi")
        await chat.finish()
    assert "chat of project" not in recording.systems[0]


async def test_a_brief_or_project_outside_the_account_starts_no_conversation(
    chat: Chat,
) -> None:
    alices = brief(chat)
    bobs = brief(chat, BOB)
    asks = [
        {"project_id": bobs.project_id, "brief_id": bobs.brief_id},
        {"project_id": bobs.project_id},
        {"project_id": alices.project_id, "brief_id": alices.brief_id},
        {"project_id": alices.project_id},
        {"project_id": bobs.project_id, "brief_id": alices.brief_id},
        {"brief_id": alices.brief_id},
        {"project_id": alices.project_id, "brief_id": alices.brief_id, "slot": 1},
    ]
    async with chat.client(BOB) as client:
        answers = [
            (await client.post("/v1/conversations", headers=JSON, content=json.dumps(one)))
            for one in asks
        ]
    assert [one.status_code for one in answers] == [201, 201, 404, 404, 404, 422, 422]
    assert not list(chat.tenants.of(AccountId(ALICE)).conversations.glob("*.json"))


async def test_the_read_answers_only_the_account_that_holds_the_conversation(
    chat: Chat,
) -> None:
    async with chat.client() as alice, chat.client(BOB) as bob, chat.client(None) as nobody:
        cid = await chat.conversation(alice)
        store.set_mode(chat.tenants.of(AccountId(ALICE)), ConversationId(cid), Mode.DESIGN)
        own = await alice.get(f"/v1/conversations/{cid}")
        other = await bob.get(f"/v1/conversations/{cid}")
        unknown = await alice.get("/v1/conversations/c_0000000000000000")
        anonymous = await nobody.get(f"/v1/conversations/{cid}")
    assert own.json()["mode"] == "design"
    assert (other.status_code, unknown.status_code, anonymous.status_code) == (404, 404, 401)
    assert not list(chat.tenants.of(AccountId(BOB)).conversations.glob("*.json"))


async def test_a_project_has_one_conversation_and_reading_it_twice_finds_the_same(
    chat: Chat,
) -> None:
    made = brief(chat)
    path = f"/v1/projects/{made.project_id}/conversation"
    async with chat.client() as alice, chat.client(BOB) as bob, chat.client(None) as nobody:
        first = await alice.get(path)
        again = await alice.get(path)
        other = await bob.get(path)
        anonymous = await nobody.get(path)
        cid = first.json()["conversation_id"]
        read = await alice.get(f"/v1/conversations/{cid}")
    assert first.status_code == 200, first.text
    assert again.json() == first.json()
    assert (read.json()["project_id"], read.json()["brief_id"]) == (made.project_id, None)
    assert (other.status_code, anonymous.status_code) == (404, 401)
    assert len(list(chat.tenants.of(AccountId(ALICE)).conversations.glob("c_*.json"))) == 1


async def test_the_first_brief_of_a_chat_binds_it_and_later_briefs_join_its_project(
    chat: Chat,
) -> None:
    async with chat.client() as client:
        cid = ConversationId(await chat.conversation(client))
        tenant = replace(chat.tenants.of(AccountId(ALICE)), conversation=cid)
        said = Channel(transcript_path(tenant.conversations, cid))
        said.append(UserSaid(text=TEXT))
        first = create_brief(tenant, CreateBriefInput())
        said.append(UserSaid(text="a lid for it"))
        second = create_brief(tenant, CreateBriefInput())
        found = await client.get(f"/v1/projects/{first.project_id}/conversation")
    assert store.read(tenant.conversations, cid).project_id == first.project_id
    assert second.project_id == first.project_id
    assert found.json()["conversation_id"] == cid


async def test_the_card_reads_what_waits_and_its_snapshot_answers_the_page_form(
    chat: Chat,
) -> None:
    made = brief(chat)
    path = f"/v1/projects/{made.project_id}/confirmation"
    async with chat.client() as alice, chat.client(BOB) as bob, chat.client(None) as nobody:
        empty = await alice.get(path)
        proposed(chat, made.brief_id)
        waiting = await alice.get(path)
        other = await bob.get(path)
        anonymous = await nobody.get(path)
        card = waiting.json()
        body = urlencode({"snapshot": card["snapshot"], "answer": "confirm", "note": ""})
        status = await chat.post_page(alice, made.project_id, body.encode())
        after = await alice.get(path)
    assert empty.json() == {"snapshot": None, "items": []}
    [item] = card["items"]
    assert (item["kind"], item["brief_id"], item["brief_text"]) == (
        "requirements",
        made.brief_id,
        TEXT,
    )
    assert [(row["headline"], row["quote"]) for row in item["rows"]] == [
        ("Mass at most 150 g", "under 150 g")
    ]
    assert (other.status_code, anonymous.status_code) == (404, 401)
    assert status == 200
    assert after.json() == {"snapshot": None, "items": []}
    tenant = chat.tenants.of(AccountId(ALICE))
    view = list_requirements(tenant, ListRequirementsInput(brief_id=made.brief_id))
    assert view.confirmed_proposal == 1
