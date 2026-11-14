import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise

import pytest

from cad.chat.guidance import CHAT_LONG, CHAT_TRIMMED_NOTICE
from cad.chat.model import Media, Message, Model, Text, ToolResult, ToolSpec
from cad.chat.window import cap_of, trim
from tests.support.chat import Chat, call, script, step

pytestmark = pytest.mark.anyio


def results(count: int, size: int = 1000) -> list[Message]:
    messages = [Message(role="user", blocks=(Text(text="make a hook"),))]
    for number in range(count):
        messages.append(
            Message(role="user", blocks=(ToolResult(call_id=f"c{number}", text="x" * size),))
        )
    return messages


def whole(messages: Sequence[Message]) -> list[bool]:
    return [
        not block.text.startswith("[earlier")
        for one in messages
        for block in one.blocks
        if isinstance(block, ToolResult)
    ]


def test_a_conversation_under_the_cap_is_sent_whole() -> None:
    sent, shortened = trim(results(5), cap=10_000)
    assert shortened == 0
    assert sent == results(5)


def test_past_the_cap_the_oldest_results_are_shortened_and_the_person_s_words_stay() -> None:
    sent, shortened = trim(results(20), cap=5_000)
    flags = whole(sent)
    assert shortened == flags.count(False) > 0
    assert flags == [False] * shortened + [True] * (20 - shortened)
    assert sent[0] == results(1)[0]
    assert all(len(block.text) < 1000 for block in sent[1].blocks if isinstance(block, ToolResult))


def test_the_newest_message_is_whole_even_when_it_alone_is_over_the_cap() -> None:
    newest = tuple(ToolResult(call_id=f"n{number}", text="y" * 10_000) for number in range(3))
    sent, shortened = trim([*results(4), Message(role="user", blocks=newest)], cap=100)
    assert shortened == 4
    assert whole(sent) == [False] * 4 + [True] * 3


def sends(steps: int) -> list[list[Message]]:
    """The transcript as each step sends it, one call and one result of varied size a step."""
    sizes = random.Random(7)
    messages = [Message(role="user", blocks=(Text(text="make a hook"),))]
    each: list[list[Message]] = []
    for number in range(steps):
        each.append(list(messages))
        messages.append(Message(role="assistant", blocks=(Text(text="Reading."),)))
        text = "x" * int(sizes.expovariate(1 / 4000))
        messages.append(Message(role="user", blocks=(ToolResult(call_id=f"c{number}", text=text),)))
    return each


def test_the_cut_moves_rarely_and_the_sent_prefix_holds_between_moves() -> None:
    cap = 60_000
    transcripts = sends(150)
    sent = [trim(one, cap) for one in transcripts]
    total = sum(len(block.text) for block in whole_results(transcripts[-1]))
    moves = 0
    for (before, cut_before), (after, cut_after) in pairwise(sent):
        assert cut_after >= cut_before
        if cut_after == cut_before:
            assert after[: len(before)] == before
        else:
            moves += 1
    assert 0 < moves <= total // (cap // 2)


def whole_results(messages: Sequence[Message]) -> list[ToolResult]:
    return [block for one in messages for block in one.blocks if isinstance(block, ToolResult)]


def test_one_attached_file_does_not_shorten_a_short_chat() -> None:
    pdf = Media(media_type="application/pdf", data="A" * 3_000_000)
    datasheet = ToolResult(call_id="pdf", text="datasheet.pdf", media=(pdf,))
    messages = [
        *results(3),
        Message(role="user", blocks=(datasheet,)),
        Message(role="user", blocks=(ToolResult(call_id="after", text="ok"),)),
    ]
    sent, shortened = trim(messages, cap=cap_of({}))
    assert shortened == 0
    assert sent == messages


def test_a_cap_comes_from_the_environment_and_falls_back() -> None:
    assert cap_of({"CAD_CHAT_CONTEXT_CHARS": "5000"}) == 5000
    assert cap_of({"CAD_CHAT_CONTEXT_CHARS": "x"}) == cap_of({})


@dataclass
class Counting:
    inner: Model
    shortened: list[int] = field(default_factory=list[int])

    async def reply(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        searches_spent: int,
    ) -> Message:
        self.shortened.append(whole(messages).count(False))
        assert CHAT_LONG in system
        return await self.inner.reply(system, messages, tools, searches_spent)


@pytest.fixture
def model() -> Model:
    steps = [step("Reading.", call("list_requirements")) for _ in range(8)]
    return Counting(script(*steps, step("Done.")))


async def test_a_long_turn_says_so_once_and_the_stored_transcript_stays_complete(
    chat: Chat, model: Counting, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CAD_CHAT_CONTEXT_CHARS", "1")
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "make a hook")
        await chat.finish()
        events = await chat.events(client, cid)
    notices = [one for one in events if one["kind"] == "context_trimmed"]
    assert [one["text"] for one in notices] == [CHAT_TRIMMED_NOTICE]
    assert model.shortened[0] == 0
    assert model.shortened[-1] > 0
    stored = [one for one in events if one["kind"] == "tool_result"]
    assert len(stored) == 8
    assert not any(one["text"].startswith("[earlier") for one in stored)
    assert "turn_failed" not in {one["kind"] for one in events}
