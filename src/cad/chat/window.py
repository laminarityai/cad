"""What a long conversation sends the model.

Each step resends the whole conversation, so tool results, the bulk of it, would grow the cost of
every step without bound. Past a cap, the oldest results are replaced by a short stub and the
newest stay whole. The person's words, the agent's words and every call stay. The stored
transcript is never touched: only what one request carries changes.

The cut moves in strides of whole results, so between two moves the sent prefix is identical and
the API's prompt cache keeps reading it.
"""

from collections.abc import Mapping, Sequence
from typing import Final

from cad.chat.model import Message, ToolResult

CAP_VARIABLE: Final = "CAD_CHAT_CONTEXT_CHARS"
DEFAULT_CAP: Final = 300_000
STRIDE: Final = 4
ALWAYS_WHOLE: Final = 2
HEAD_CHARS: Final = 300


def cap_of(environ: Mapping[str, str]) -> int:
    raw = environ.get(CAP_VARIABLE, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_CAP


def trim(messages: Sequence[Message], cap: int) -> tuple[list[Message], int]:
    """The messages to send, and how many results were shortened. Results kept whole add up to at
    most `cap` characters, except that the newest `ALWAYS_WHOLE` are always whole."""
    weights = [
        _weight(block) for one in messages for block in one.blocks if isinstance(block, ToolResult)
    ]
    kept = _first_whole(weights, cap)
    if kept == 0:
        return list(messages), 0
    seen = 0
    trimmed: list[Message] = []
    for one in messages:
        blocks = list(one.blocks)
        for at, block in enumerate(blocks):
            if isinstance(block, ToolResult):
                if seen < kept:
                    blocks[at] = _stub(block)
                seen += 1
        trimmed.append(Message(role=one.role, blocks=tuple(blocks)))
    return trimmed, kept


def _weight(block: ToolResult) -> int:
    return len(block.text) + sum(len(one.data) for one in block.media)


def _first_whole(weights: list[int], cap: int) -> int:
    """The index, a multiple of `STRIDE`, of the first result kept whole."""
    if sum(weights) <= cap:
        return 0
    newest = max(len(weights) - ALWAYS_WHOLE, 0)
    for start in range(0, len(weights), STRIDE):
        if start >= newest or sum(weights[start:]) <= cap:
            return min(start, newest)
    return newest


def _stub(block: ToolResult) -> ToolResult:
    head = block.text[:HEAD_CHARS]
    more = len(block.text) - len(head)
    left = f"\n[the rest, {more} characters, is left out]" if more > 0 else ""
    return ToolResult(
        call_id=block.call_id,
        text=f"[earlier result, shortened to keep the conversation short. Read it again with "
        f"the tool, or with list_requirements, scorecard or variant_set.]\n{head}{left}",
        is_error=block.is_error,
    )
