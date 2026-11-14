from collections.abc import Sequence
from pathlib import Path
from typing import Final, NamedTuple

from cad.briefs.model import MAX_BRIEF_CHARS, SAID_SEPARATOR
from cad.briefs.said import Spoken, Words
from cad.briefs.store import BriefRefused
from cad.chat.log import Stamped, ToolCalled, ToolReturned, UserSaid, person_said, transcript
from cad.conversations.model import ConversationId

ASK_QUESTIONS: Final = "ask_questions"
CREATE_BRIEF: Final = "create_brief"

CHAT_HINT = (
    "copy the words exactly from the brief or from one of the person's messages in this "
    "conversation; never quote words the person did not say"
)
OUTSIDE_HINT = "copy the words exactly from the brief, or pass the person's new words as said"


class WordsRefused(BriefRefused):
    pass


class FirstWords(NamedTuple):
    """The words a new brief holds: the request, and the person's answers to the questions the
    agent asked about it, each stored as said so a quote from an answer is the person's own."""

    request: Spoken
    answers: tuple[Spoken, ...] = ()


def first_words(directory: Path, cid: ConversationId | None, given: str | None) -> FirstWords:
    if cid is None:
        if given is None:
            raise WordsRefused("pass text: the person's words, verbatim")
        return FirstWords(Spoken(None, given))
    if given is not None:
        raise WordsRefused(
            "in chat pass no text: the server copies the person's newest message into the brief"
        )
    stamped = transcript(directory, cid)
    said = [(one.seq, one.event.text) for one in stamped if isinstance(one.event, UserSaid)]
    if not said:
        raise WordsRefused("the person has said nothing in this conversation yet")
    asked = _asked_at(stamped)
    newest = FirstWords(Spoken(*said[-1]))
    if asked is None:
        return newest
    request = [Spoken(*one) for one in said if one[0] < asked]
    answers = [Spoken(*one) for one in said if one[0] > asked]
    if not request or not answers:
        return newest
    return FirstWords(request[-1], _fitting(request[-1], answers))


def _asked_at(stamped: Sequence[Stamped]) -> int | None:
    """The seq of the first ask_questions that returned since the newest brief was stored."""
    called = {
        one.event.call_id: (one.seq, one.event.name)
        for one in stamped
        if isinstance(one.event, ToolCalled)
    }
    asked: int | None = None
    for one in reversed(stamped):
        event = one.event
        if not isinstance(event, ToolReturned) or event.is_error or event.call_id not in called:
            continue
        seq, name = called[event.call_id]
        if name == CREATE_BRIEF:
            break
        if name == ASK_QUESTIONS:
            asked = seq
    return asked


def _fitting(request: Spoken, answers: Sequence[Spoken]) -> tuple[Spoken, ...]:
    """The answers that fit in one brief after the request, oldest first."""
    room = MAX_BRIEF_CHARS - len(request.text)
    kept: list[Spoken] = []
    for one in answers:
        room -= len(SAID_SEPARATOR) + len(one.text)
        if room < 0:
            break
        kept.append(one)
    return tuple(kept)


def later_words(directory: Path, cid: ConversationId | None, given: str | None) -> Words:
    if cid is None:
        heard = () if given is None else (Spoken(None, given),)
        return Words(newest_first=heard, refusal_hint=OUTSIDE_HINT)
    if given is not None:
        raise WordsRefused(
            "in chat pass no said: the server finds the words a quote comes from in the "
            "person's messages"
        )
    said = person_said(directory, cid)
    return Words(newest_first=tuple(Spoken(*one) for one in reversed(said)), refusal_hint=CHAT_HINT)
