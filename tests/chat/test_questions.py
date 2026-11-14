import json
from typing import Any

import pytest

from cad.accounts.principal import AccountId
from cad.briefs import store
from cad.briefs.origins import quoted as quote_of
from cad.chat.model import Model
from cad.chat.scripted import Call
from cad.operations.questions import ASKED_IN_CHAT
from tests.support.chat import ALICE, TEXT, Chat, call, script, step

pytestmark = pytest.mark.anyio

QUESTIONS = [
    {
        "question": "How heavy may it be?",
        "default": "at most 200 g",
        "why": "Mass sets how thick the plate is.",
        "suggestions": ["at most 100 g", "at most 200 g"],
    },
    {"question": "What does it mount on?", "default": "a flat wall", "why": "It sets the holes."},
]
ANSWER = "How heavy may it be?: at most 120 g\nUse your defaults for the rest."
THEIRS = "at most 120 g\nUse your defaults for the rest."
UNDER_120 = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 120, "unit": "g"}},
    "quote": "at most 120 g",
}


@pytest.fixture
def model() -> Model:
    return script(
        step("A few questions first.", call("ask_questions", questions=QUESTIONS)),
        step("Answer the questions on the card."),
        step("Storing it.", call("create_brief")),
        step(
            "Proposing.",
            call(
                "propose_requirements",
                brief_id="${create_brief.brief_id}",
                requirements=[UNDER_120],
            ),
        ),
        step("Done."),
    )


def results(events: list[Any]) -> list[tuple[bool, str]]:
    return [(one["is_error"], one["text"]) for one in events if one["kind"] == "tool_result"]


async def test_the_brief_holds_the_request_and_the_answers_and_a_number_in_an_answer_is_stated(
    chat: Chat,
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, TEXT)
        await chat.finish()
        asked_only = await chat.events(client, cid)
        await chat.say(client, cid, ANSWER)
        await chat.finish()
        events = await chat.events(client, cid)
    assert [one["kind"] for one in asked_only][-3:] == ["tool_result", "agent", "turn_ended"]
    (_, asked), (_, created), (refused, proposed) = results(events)
    assert json.loads(asked) == {
        "questions": [{**QUESTIONS[0]}, {**QUESTIONS[1], "suggestions": []}],
        "next": ASKED_IN_CHAT,
    }
    brief = json.loads(created)
    assert brief["text"] == f"{TEXT}\n\n{THEIRS}"
    assert not refused, proposed
    roots = chat.tenants.of(AccountId(ALICE)).roots
    state = store.read_state(roots, brief["brief_id"])
    assert state.brief.text == f"{TEXT}\n\n{THEIRS}"
    [requirement] = state.proposals[0].requirements
    assert quote_of(state.brief.text, requirement.origin)[1] == "at most 120 g"


LEADING = "Most impellers this size weigh at most 30 g. What does it pump?"


def propose(quote: str, grams: int) -> Call:
    target = {"kind": "max_mass", "mass": {"magnitude": grams, "unit": "g"}}
    return call(
        "propose_requirements",
        brief_id="${create_brief.brief_id}",
        requirements=[{"target": target, "quote": quote}],
    )


LEADING_SCRIPT = script(
    step("A question.", call("ask_questions", questions=[{**QUESTIONS[1], "question": LEADING}])),
    step("Answer on the card."),
    step("Storing it.", call("create_brief")),
    step("Proposing.", propose("weigh at most 30 g", 30)),
    step("Proposing again.", propose("at most 25 g", 25)),
    step("Done."),
)


@pytest.mark.parametrize("model", [LEADING_SCRIPT])
async def test_a_quote_from_the_question_is_refused_and_one_from_the_typed_answer_is_kept(
    chat: Chat,
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, TEXT)
        await chat.finish()
        await chat.say(client, cid, f"{LEADING}: sea water, at most 25 g")
        await chat.finish()
        events = await chat.events(client, cid)
    _, (_, created), (from_question, _), (from_answer, proposed) = results(events)
    assert from_question
    assert not from_answer, proposed
    assert json.loads(created)["text"] == f"{TEXT}\n\nsea water, at most 25 g"
