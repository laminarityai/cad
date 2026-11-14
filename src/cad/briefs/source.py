from collections.abc import Sequence
from pathlib import Path
from typing import Final, NamedTuple

from pydantic import BaseModel, ValidationError

from cad.briefs.model import MAX_BRIEF_CHARS, SAID_SEPARATOR
from cad.briefs.said import Spoken, Words
from cad.briefs.store import BriefRefused
from cad.chat.log import Stamped, ToolCalled, ToolReturned, UserSaid, transcript
from cad.conversations.model import ConversationId

ASK_QUESTIONS: Final = "ask_questions"
CREATE_BRIEF: Final = "create_brief"
ANSWERS_TO: Final = ": "

CHAT_HINT = (
    "copy the words exactly from the brief or from one of the person's messages in this "
    "conversation; never quote words the person did not say"
)
OUTSIDE_HINT = "copy the words exactly from the brief, or pass the person's new words as said"


class WordsRefused(BriefRefused):
    pass


class FirstWords(NamedTuple):
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
    said = _person_words(stamped)
    if not said:
        raise WordsRefused("the person has said nothing in this conversation yet")
    asked = _first_ask_since_brief(stamped)
    newest = FirstWords(Spoken(*said[-1]))
    if asked is None:
        return newest
    request = [Spoken(*one) for one in said if one[0] < asked]
    answers = [Spoken(*one) for one in said if one[0] > asked]
    if not request or not answers:
        return newest
    return FirstWords(request[-1], _fitting(request[-1], answers))


def _first_ask_since_brief(stamped: Sequence[Stamped]) -> int | None:
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
    said = _person_words(transcript(directory, cid))
    return Words(newest_first=tuple(Spoken(*one) for one in reversed(said)), refusal_hint=CHAT_HINT)


class _Question(BaseModel):
    question: str


class _Asked(BaseModel):
    questions: list[_Question]


def _questions_in(result: str) -> list[str]:
    try:
        return [one.question for one in _Asked.model_validate_json(result).questions]
    except ValidationError:
        return []


def _person_words(stamped: Sequence[Stamped]) -> list[tuple[int, str]]:
    calls: set[str] = set()
    asked: set[str] = set()
    said: list[tuple[int, str]] = []
    for one in stamped:
        event = one.event
        if isinstance(event, ToolCalled) and event.name == ASK_QUESTIONS:
            calls.add(event.call_id)
        elif isinstance(event, ToolReturned) and not event.is_error and event.call_id in calls:
            calls.discard(event.call_id)
            asked.update(_questions_in(event.text))
        elif isinstance(event, UserSaid):
            said.append((one.seq, _answers_only(event.text, asked)))
    return said


def _answers_only(text: str, asked: set[str]) -> str:
    prefixes = sorted((f"{one}{ANSWERS_TO}" for one in asked), key=len, reverse=True)
    lines = text.split("\n")
    for at, line in enumerate(lines):
        prefix = next((one for one in prefixes if line.startswith(one)), "")
        lines[at] = line.removeprefix(prefix)
    return "\n".join(lines)
