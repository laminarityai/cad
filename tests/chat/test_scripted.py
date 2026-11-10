import json
from pathlib import Path

import pytest

from cad.chat.model import Message, ModelUnavailable, Text, ToolResult, ToolUse
from cad.chat.scripted import EXHAUSTED, Scripted

pytestmark = pytest.mark.anyio

SCRIPT = {
    "steps": [
        {"text": "Storing it.", "calls": [{"name": "create_brief", "input": {"text": "a hook"}}]},
        {
            "calls": [
                {
                    "name": "propose_requirements",
                    "input": {
                        "brief_id": "${create_brief.brief_id}",
                        "note": "for ${create_brief.project_id}!",
                        "code": "@file:part.py",
                    },
                }
            ]
        },
        {"text": "Done."},
    ]
}


def user(text: str) -> Message:
    return Message(role="user", blocks=(Text(text=text),))


def answered(replied: Message, text: str) -> Message:
    (use,) = replied.calls
    return Message(role="user", blocks=(ToolResult(call_id=use.id, text=text, is_error=False),))


@pytest.fixture
def scripted(tmp_path: Path) -> Scripted:
    (tmp_path / "script.json").write_text(json.dumps(SCRIPT))
    (tmp_path / "part.py").write_text("result = 1\n")
    return Scripted.load(str(tmp_path / "script.json"))


async def test_each_step_answers_the_next_assistant_message(scripted: Scripted) -> None:
    first = await scripted.reply("", [user("hi")], [])
    assert first.blocks[0] == Text(text="Storing it.")
    (use,) = first.calls
    assert (use.name, use.input, use.id) == ("create_brief", {"text": "a hook"}, "script_0_0")
    result = answered(first, json.dumps({"brief_id": "b1", "project_id": "p1"}))
    second = await scripted.reply("", [user("hi"), first, result], [])
    (use,) = second.calls
    assert use.input == {"brief_id": "b1", "note": "for p1!", "code": "result = 1\n"}
    third = await scripted.reply(
        "", [user("hi"), first, result, second, answered(second, "{}")], []
    )
    assert third.blocks == (Text(text="Done."),)
    assert third.calls == ()


async def test_a_script_that_ran_out_says_so(scripted: Scripted) -> None:
    done = [Message(role="assistant", blocks=(Text(text="x"),))] * 3
    ended = await scripted.reply("", done, [])
    assert ended.blocks == (Text(text=EXHAUSTED),)


async def test_a_reference_no_result_holds_stops_the_turn(scripted: Scripted) -> None:
    first = await scripted.reply("", [user("hi")], [])
    (use,) = first.calls
    broken = Message(
        role="user", blocks=(ToolResult(call_id=use.id, text='{"other": 1}', is_error=False),)
    )
    with pytest.raises(ModelUnavailable, match=r"create_brief\.brief_id"):
        await scripted.reply("", [user("hi"), first, broken], [])


async def test_the_double_keeps_no_state_between_replies(scripted: Scripted) -> None:
    once = await scripted.reply("", [user("hi")], [])
    again = await scripted.reply("", [user("hi")], [])
    assert once == again
    assert isinstance(once.blocks[1], ToolUse)
