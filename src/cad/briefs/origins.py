"""Where a requirement's words come from: the brief, or a document the person added (ADR-0012)."""

from typing import Annotated, Final, Literal

from pydantic import Field

from cad.frozen import Frozen

MAX_QUOTE_CHARS: Final = 2_000
MAX_FILE_NAME_CHARS: Final = 200
FILE_ID_PATTERN: Final = r"^file-[0-9a-f]{16}$"
YOUR_WORDS: Final = "your words"


class BriefSpan(Frozen):
    """Characters [start, end) of the brief text, resolved by the store from a verbatim quote."""

    kind: Literal["brief_text"] = "brief_text"
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]


class FileQuote(Frozen):
    """Words from a document the person added. `checked` says the server found them in the
    file's text; an image or a scanned PDF is read by the agent, and its quote is labelled as
    such."""

    kind: Literal["file"] = "file"
    file_id: Annotated[str, Field(pattern=FILE_ID_PATTERN)]
    name: Annotated[str, Field(min_length=1, max_length=MAX_FILE_NAME_CHARS)]
    quote: Annotated[str, Field(min_length=1, max_length=MAX_QUOTE_CHARS)]
    checked: bool


type Origin = Annotated[BriefSpan | FileQuote, Field(discriminator="kind")]


def quoted(brief_text: str, origin: Origin) -> tuple[str, str]:
    """The source a person reads, such as "your words", and the words themselves."""
    if isinstance(origin, BriefSpan):
        return YOUR_WORDS, brief_text[origin.start : origin.end]
    if origin.checked:
        return origin.name, origin.quote
    return f"{origin.name}, as the agent read it", origin.quote
