import pytest
from mcp import Client

from cad.operations.questions import ASKED_OUTSIDE
from cad.server.app import build_server

pytestmark = pytest.mark.anyio


def questions(count: int) -> list[dict[str, object]]:
    return [
        {"question": f"Question {n}?", "default": "a default", "why": "It changes the shape."}
        for n in range(count)
    ]


async def test_another_client_is_told_to_ask_the_questions_in_its_reply() -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("ask_questions", {"questions": questions(5)})
    assert not result.is_error
    assert result.structured_content is not None
    assert len(result.structured_content["questions"]) == 5
    assert result.structured_content["next"] == ASKED_OUTSIDE


@pytest.mark.parametrize("count", [0, 6])
async def test_no_questions_or_a_sixth_is_refused(count: int) -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("ask_questions", {"questions": questions(count)})
    assert result.is_error


async def test_a_fourth_suggestion_is_refused() -> None:
    [one] = questions(1)
    asked = {**one, "suggestions": ["a", "b", "c", "d"]}
    async with Client(build_server()) as client:
        result = await client.call_tool("ask_questions", {"questions": [asked]})
    assert result.is_error
