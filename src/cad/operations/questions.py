from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from cad.briefs.source import ASK_QUESTIONS
from cad.operations.guidance import READ_FIRST
from cad.operations.model import Audience, Input, Tenant, operation

MAX_QUESTIONS: Final = 5
MAX_SUGGESTIONS: Final = 3
MAX_QUESTION_CHARS: Final = 300
MAX_ANSWER_CHARS: Final = 200
ONE_LINE: Final = r"^[^\r\n]*$"

ASK = (
    "Ask the person a few questions about a fresh brief, once, before its first build. Pass 1 "
    "to 5 questions, each with the question, the default you will use when they do not "
    "answer, one line of why it changes the design, and up to 3 suggested answers. Never ask "
    "the person to pick among options you can build, and never ask about a change to a built "
    "option. A default is your assumption: it is never a target until the person states it. "
    "Put a number you would propose in a suggested answer or the default, never only in the "
    "question, because only what the person picks or types is theirs. " + READ_FIRST
)

ASKED_IN_CHAT: Final = (
    "The person sees these questions on a card in this chat, each with its default and "
    "suggested answers, below your message. End your message now with one short sentence that "
    "points at the card below, without listing the questions again. "
    "Build nothing and call nothing more: their answer comes as their next message."
)

ASKED_OUTSIDE: Final = (
    "Ask the person these questions in your reply, each with its default and why, and end your "
    "reply. Build nothing until they answer. Then pass their request and their answers, "
    "verbatim, as create_brief's text."
)

type Answer = Annotated[str, Field(min_length=1, max_length=MAX_ANSWER_CHARS)]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_CHARS, pattern=ONE_LINE)]
    default: Answer
    why: Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_CHARS)]
    suggestions: Annotated[list[Answer], Field(max_length=MAX_SUGGESTIONS)] = []


class AskQuestionsInput(Input):
    questions: Annotated[list[Question], Field(min_length=1, max_length=MAX_QUESTIONS)]


class Asked(BaseModel):
    questions: list[Question]
    next: str


def ask_questions(tenant: Tenant, arguments: AskQuestionsInput) -> Asked:
    told = ASKED_OUTSIDE if tenant.conversation is None else ASKED_IN_CHAT
    return Asked(questions=arguments.questions, next=told)


OPERATIONS: Final = (
    operation(
        name=ASK_QUESTIONS,
        audience=Audience.AGENT,
        description=ASK,
        input=AskQuestionsInput,
        output=Asked,
        run=ask_questions,
    ),
)
