import json
from pathlib import Path
from typing import Any, Final, cast

CARD_TOOLS: Final = ("mcp__cad__score_variant", "mcp__cad__scorecard")


def cards_in(events: list[dict[str, Any]]) -> list[str]:
    asked: set[str] = set()
    cards: list[str] = []
    for event in events:
        message = cast(dict[str, Any], event.get("message", {}))
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in cast(list[dict[str, Any]], content):
            if block.get("type") == "tool_use" and block.get("name") in CARD_TOOLS:
                asked.add(cast(str, block["id"]))
            elif (
                block.get("type") == "tool_result"
                and not block.get("is_error")
                and block.get("tool_use_id") in asked
            ):
                cards.append(_text_of(block.get("content")))
    return cards


def read_cards(transcript: Path) -> list[str]:
    try:
        events = cast(list[dict[str, Any]], json.loads(transcript.read_text()))
    except (OSError, ValueError):
        return []
    return cards_in(events)


def _text_of(content: object) -> str:
    if isinstance(content, str):
        return content
    parts = cast(list[dict[str, Any]], content) if isinstance(content, list) else []
    return "".join(cast(str, part.get("text", "")) for part in parts)
