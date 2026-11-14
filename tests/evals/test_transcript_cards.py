from typing import Any

import pytest
from transcript_cards import cards_in


def turn(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"message": {"content": list(blocks)}}


def test_a_transcript_with_two_results_for_one_call_is_refused() -> None:
    asked = turn({"type": "tool_use", "id": "t1", "name": "mcp__cad__scorecard"})
    answer = turn({"type": "tool_result", "tool_use_id": "t1", "content": "{}"})
    assert cards_in([asked, answer]) == ["{}"]
    with pytest.raises(ValueError, match="more than one tool_result for tool_use_id 't1'"):
        cards_in([asked, answer, answer])
