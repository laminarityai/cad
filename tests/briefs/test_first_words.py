from pathlib import Path

from cad.briefs.said import Spoken
from cad.briefs.source import ASK_QUESTIONS, CREATE_BRIEF, FirstWords, first_words
from cad.chat.log import Channel, Event, ToolCalled, ToolReturned, UserSaid, transcript_path
from cad.conversations.model import ConversationId

CID = ConversationId("conv_0123456789abcdef")


def told(tmp_path: Path, *events: Event) -> FirstWords:
    channel = Channel(transcript_path(tmp_path, CID))
    for one in events:
        channel.append(one)
    return first_words(tmp_path, CID, None)


def called(call_id: str, name: str, *, failed: bool = False) -> tuple[Event, Event]:
    return (
        ToolCalled(call_id=call_id, name=name, input={"questions": []}),
        ToolReturned(call_id=call_id, text="{}", is_error=failed),
    )


def test_with_no_questions_the_brief_is_the_newest_message(tmp_path: Path) -> None:
    words = told(tmp_path, UserSaid(text="a hook"), UserSaid(text="a plate"))
    assert words == FirstWords(Spoken(2, "a plate"))


def test_after_questions_the_brief_is_the_request_with_every_answer(tmp_path: Path) -> None:
    words = told(
        tmp_path,
        UserSaid(text="an impeller"),
        *called("a", ASK_QUESTIONS),
        UserSaid(text="Diameter: 40 mm"),
        UserSaid(text="and it is for water"),
    )
    assert words == FirstWords(
        Spoken(1, "an impeller"), (Spoken(4, "Diameter: 40 mm"), Spoken(5, "and it is for water"))
    )


def test_questions_that_failed_or_came_before_a_stored_brief_are_not_answered(
    tmp_path: Path,
) -> None:
    refused = told(
        tmp_path,
        UserSaid(text="a plate"),
        *called("a", ASK_QUESTIONS, failed=True),
        UserSaid(text="M5"),
    )
    assert refused == FirstWords(Spoken(4, "M5"))
    later = told(
        tmp_path / "later",
        UserSaid(text="a plate"),
        *called("a", ASK_QUESTIONS),
        UserSaid(text="M5 holes"),
        *called("b", CREATE_BRIEF),
        UserSaid(text="now a lid"),
    )
    assert later == FirstWords(Spoken(7, "now a lid"))


def test_questions_asked_and_a_brief_stored_in_one_turn_leave_the_request_alone(
    tmp_path: Path,
) -> None:
    words = told(tmp_path, UserSaid(text="a plate"), *called("a", ASK_QUESTIONS))
    assert words == FirstWords(Spoken(1, "a plate"))
