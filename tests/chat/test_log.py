import asyncio
from pathlib import Path

import pytest

from cad.chat.log import (
    STOP_NOTICE,
    AgentSaid,
    Channel,
    ToolCalled,
    ToolReturned,
    TurnEnded,
    UserSaid,
    line,
    messages_of,
)
from cad.chat.model import Text, ToolResult, ToolUse

pytestmark = pytest.mark.anyio


def test_a_transcript_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "chat" / "c1.jsonl"
    first = Channel(path)
    first.append(UserSaid(text="hi"))
    first.append(AgentSaid(text="hello"))
    second = Channel(path)
    assert [one.seq for one in second.after(0)] == [1, 2]
    assert second.append(TurnEnded()).seq == 3
    assert [one.seq for one in second.after(1)] == [2, 3]


def test_a_line_a_crash_cut_short_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "c1.jsonl"
    Channel(path).append(UserSaid(text="hi"))
    with path.open("ab") as file:
        file.write(b'{"seq": 2, "event": {"kind": "ag')
    held = Channel(path)
    assert len(held.after(0)) == 1
    assert held.append(AgentSaid(text="again")).seq == 2
    assert [one.seq for one in Channel(path).after(0)] == [1, 2]


def test_a_disk_that_fills_while_the_cut_line_is_dropped_keeps_the_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "c1.jsonl"
    Channel(path).append(UserSaid(text="hi"))
    with path.open("ab") as file:
        file.write(b'{"seq": 2, "event": {"kind": "ag')
    kept = path.read_bytes()

    def fills_halfway(self: Path, data: bytes) -> int:
        with self.open("wb") as file:
            file.write(data[: len(data) // 2])
        raise OSError("no space left on device")

    monkeypatch.setattr(Path, "write_bytes", fills_halfway)
    with pytest.raises(OSError, match="no space"):
        Channel(path)
    assert path.read_bytes() == kept
    assert [p.name for p in tmp_path.iterdir()] == [path.name]


async def test_a_waiter_wakes_for_the_next_append(tmp_path: Path) -> None:
    channel = Channel(tmp_path / "c1.jsonl")
    waiting = asyncio.create_task(channel.wait_change(0, ""))
    await asyncio.sleep(0)
    channel.append(UserSaid(text="hi"))
    await asyncio.wait_for(waiting, 1)
    assert [one.seq for one in channel.after(0)] == [1]


def test_a_server_sent_event_carries_the_seq_as_its_id(tmp_path: Path) -> None:
    stamped = Channel(tmp_path / "c1.jsonl").append(UserSaid(text="hi"))
    assert (
        line(stamped)
        == 'id: 1\nevent: user\ndata: {"kind":"user","text":"hi","selection":null}\n\n'
    )


def test_the_model_sees_calls_with_their_results_in_order() -> None:
    messages = messages_of(
        [
            UserSaid(text="build"),
            AgentSaid(text="on it"),
            ToolCalled(call_id="a", name="create_brief", input={"text": "x"}),
            ToolReturned(call_id="a", text="{}", is_error=False),
            AgentSaid(text="done"),
            TurnEnded(),
        ]
    )
    assert [one.role for one in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[1].blocks == (
        Text(text="on it"),
        ToolUse(id="a", name="create_brief", input={"text": "x"}),
    )
    assert messages[2].blocks == (ToolResult(call_id="a", text="{}", is_error=False),)


def test_a_call_a_dead_turn_left_unanswered_gets_an_error_result() -> None:
    messages = messages_of(
        [
            UserSaid(text="build"),
            ToolCalled(call_id="a", name="create_brief", input={}),
            UserSaid(text="again"),
        ]
    )
    assert [one.role for one in messages] == ["user", "assistant", "user"]
    assert messages[2].blocks == (
        ToolResult(call_id="a", text=STOP_NOTICE, is_error=True),
        Text(text="again"),
    )
