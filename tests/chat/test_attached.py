"""A PDF or an image that read_file names reaches the model as a file, never through the log."""

import base64
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from cad.accounts.principal import AccountId, PersonSession
from cad.briefs.store import create_brief
from cad.chat.anthropic_model import _param  # pyright: ignore[reportPrivateUsage]
from cad.chat.model import Attached, Media, Message, Model, ToolResult, ToolSpec
from cad.chat.turn import _media_of  # pyright: ignore[reportPrivateUsage]
from cad.projects.model import new_project_id
from cad.uploads import store
from cad.uploads.model import kind_of
from tests.support.chat import ALICE, Chat, call, script, step

pytestmark = pytest.mark.anyio
PDF = b"%PDF-1.7 the motor's datasheet"
PERSON = PersonSession(account=AccountId(ALICE), session_id="sess_1")


@dataclass
class Seen:
    inner: Model
    messages: list[list[Message]] = field(default_factory=list[list[Message]])

    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message:
        self.messages.append(list(messages))
        return await self.inner.reply(system, messages, tools)


@pytest.fixture
def model() -> Model:
    """The test gives it its script once it knows the file's id."""
    return Seen(script())


def media_of(messages: list[Message]) -> list[Media]:
    return [
        one
        for message in messages
        for block in message.blocks
        if isinstance(block, ToolResult)
        for one in block.media
    ]


async def test_a_pdf_reaches_the_model_on_this_turn_and_the_next(chat: Chat, model: Seen) -> None:
    tenant = chat.tenants.of(AccountId(ALICE))
    project = create_brief(tenant.roots, "A clip for the motor", new_project_id()).project
    pdf = store.add_document(
        tenant.roots.projects, project, "sheet.pdf", kind_of("sheet.pdf"), PDF, PERSON
    )
    model.inner = script(
        step("Reading.", call("read_file", project_id=project, file_id=pdf.id)),
        step("Read it."),
        step("Again."),
    )
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "read the datasheet")
        await chat.finish()
        await chat.say(client, cid, "and again")
        await chat.finish()
        events = await chat.events(client, cid)
    expected = [Media(media_type="application/pdf", data=base64.b64encode(PDF).decode())]
    assert media_of(model.messages[1]) == expected
    assert media_of(model.messages[2]) == expected
    [returned] = [one for one in events if one["kind"] == "tool_result"]
    assert returned["attached"] == [{"project_id": project, "file_id": pdf.id}]
    assert base64.b64encode(PDF).decode() not in str(events)


async def test_a_withheld_pdf_is_refused_by_read_file_and_never_reaches_the_model(
    chat: Chat, model: Seen
) -> None:
    tenant = chat.tenants.of(AccountId(ALICE))
    project = create_brief(tenant.roots, "A clip for the motor", new_project_id()).project
    pdf = store.add_document(
        tenant.roots.projects, project, "din.pdf", kind_of("din.pdf"), PDF, PERSON, True
    )
    model.inner = script(
        step("Reading.", call("read_file", project_id=project, file_id=pdf.id)),
        step("It is withheld."),
    )
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "read the standard")
        await chat.finish()
        events = await chat.events(client, cid)
    assert media_of(model.messages[1]) == []
    [returned] = [one for one in events if one["kind"] == "tool_result"]
    assert returned["is_error"] is True
    assert "kept from you" in returned["text"]
    assert base64.b64encode(PDF).decode() not in str(events)


async def test_the_chat_leaves_a_withheld_pdf_out_even_when_a_result_names_it(
    chat: Chat,
) -> None:
    tenant = chat.tenants.of(AccountId(ALICE))
    project = create_brief(tenant.roots, "A clip for the motor", new_project_id()).project
    pdf = store.add_document(
        tenant.roots.projects, project, "din.pdf", kind_of("din.pdf"), PDF, PERSON, True
    )
    named = ToolResult(
        call_id="c1", text="{}", attached=(Attached(project_id=project, file_id=pdf.id),)
    )
    sent = _media_of(tenant, named)  # pyright: ignore[reportPrivateUsage]
    assert sent.media == ()
    assert sent.text == "{}\ndin.pdf is withheld from you"


def test_the_anthropic_request_carries_a_pdf_as_a_document_and_an_image_as_an_image() -> None:
    result = ToolResult(
        call_id="c1",
        text="{}",
        media=(
            Media(media_type="application/pdf", data="UERG"),
            Media(media_type="image/png", data="iVBO"),
        ),
    )
    [sent] = _param(Message(role="user", blocks=(result,)))["content"]
    assert isinstance(sent, dict)
    content = sent.get("content")
    assert isinstance(content, list)
    blocks = cast(list[dict[str, Any]], content)
    assert [one["type"] for one in blocks] == ["text", "document", "image"]
