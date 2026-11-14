"""What a long conversation sends the model.

Each step resends the whole conversation, so tool results, the bulk of it, would grow the cost of
every step without bound. Past a cap, the oldest results are replaced by a short stub and the
newest stay whole. The person's words, the agent's words and every call stay. The stored
transcript is never touched: only what one request carries changes.

Moving the cut rewrites the API's prompt cache from the first stub on, at the cache-write price,
so the cut moves rarely: each move takes the whole results down to half the cap. Between moves
the sent prefix is identical and the cache keeps reading it.

The default cap aims to keep a trimmed conversation of about 80 steps under the 100K-token prompt
above which Claude Haiku 5.5 bills five times the rate. The system prompt and tools are about 37K
tokens, and tool results run about 2 characters a token, so 60000 characters of results stay
near 30K tokens and leave the rest for the agent's words and calls. That holds for results that
average about 4000 characters. The agent's words and calls are never capped, so a session with
larger results or long calls can pass 100K: a simulation with real result sizes put about 6 of
80 steps over, the highest near 107K.
"""

from collections.abc import Mapping, Sequence
from typing import Final

from cad.chat.model import Message, ToolResult

CAP_VARIABLE: Final = "CAD_CHAT_CONTEXT_CHARS"
DEFAULT_CAP: Final = 60_000
MEDIA_CHARS: Final = 10_000
"""The weight of one attached image or PDF. A high-resolution image costs up to about 4,800
tokens, about 10000 characters of text, whatever the size of its base64."""
HEAD_CHARS: Final = 300


def cap_of(environ: Mapping[str, str]) -> int:
    raw = environ.get(CAP_VARIABLE, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_CAP


def trim(messages: Sequence[Message], cap: int) -> tuple[list[Message], int]:
    """The messages to send, and how many of the oldest results were shortened."""
    cut = _cut(messages, cap)
    if cut == 0:
        return list(messages), 0
    seen = 0
    trimmed: list[Message] = []
    for one in messages:
        blocks = list(one.blocks)
        for at, block in enumerate(blocks):
            if isinstance(block, ToolResult):
                if seen < cut:
                    blocks[at] = _stub(block)
                seen += 1
        trimmed.append(Message(role=one.role, blocks=tuple(blocks)))
    return trimmed, cut


def _cut(messages: Sequence[Message], cap: int) -> int:
    """How many of the oldest results to shorten. The conversation is replayed one message at a
    time. When the whole results pass `cap`, the cut moves forward until they are at most half of
    it, never into the message just added, which the model has not read yet. A conversation that
    grows by a message keeps every earlier cut, so the cut depends on the stored transcript
    alone."""
    weights: list[int] = []
    cut = 0
    whole = 0
    for one in messages:
        newest = len(weights)
        added = [_weight(block) for block in one.blocks if isinstance(block, ToolResult)]
        weights.extend(added)
        whole += sum(added)
        if whole > cap:
            while cut < newest and whole > cap // 2:
                whole -= weights[cut]
                cut += 1
    return cut


def _weight(block: ToolResult) -> int:
    return len(block.text) + MEDIA_CHARS * len(block.media)


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
