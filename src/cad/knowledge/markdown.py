"""Where a corpus file's sections start, read the way CommonMark renders the file.

A section starts where a reviewer sees a heading in the rendered file. The one accepted form is
`## Title` at the start of a line. Any other line that CommonMark renders as a heading is refused
with its line number, so it is never merged silently into the section above: an indented or
tab-separated `##`, `#` or `###` and deeper, a closing `#`, a heading inside a quote or a list
item, and a line of text over `---` or `===`. `##Title` with no space renders as text and stays
text. The refusal leans wide where rendering depends on context: a `---` under a comment line is
refused although it renders as a rule, and the error says to leave a blank line above it.

Inside a fenced code block every line is text. A fence opens on up to three spaces and three or
more backticks or tildes, and closes only on a fence of the same character at least as long, so
three backticks inside a four-backtick block are text, and "```x```" on one line is inline code.
"""

import re
from dataclasses import dataclass
from typing import Final

HEADING: Final = re.compile(r"## +(?P<title>\S.*?)[ \t]*")
CLOSING_HASHES: Final = re.compile(r"(?:^|[ \t])#+$")
CONTAINERS: Final = re.compile(r"(?:[ \t]*(?:>|[-+*](?=[ \t])|\d{1,9}[.)](?=[ \t])))*")
ATX: Final = re.compile(r" {0,3}#{1,6}(?:[ \t]|$)")
SETEXT: Final = re.compile(r" {0,3}(?:=+|-+)[ \t]*")
FENCE: Final = re.compile(r" {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)")


@dataclass(frozen=True, slots=True)
class Heading:
    title: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Body:
    headings: list[Heading]
    visible: str
    """The body with each fenced code block blanked out, offsets kept, for finding comments."""
    problems: list[str]


def _fence(line: str, open_fence: str | None) -> str | None:
    """The fence open after `line`, read the CommonMark way, or None outside any fence."""
    marker = FENCE.match(line)
    if marker is None:
        return open_fence
    fence, info = marker["fence"], marker["info"]
    if open_fence is None:
        return None if fence[0] == "`" and "`" in info else fence
    closes = fence[0] == open_fence[0] and len(fence) >= len(open_fence) and not info.strip()
    return None if closes else open_fence


def scan(body: str, first_line: int) -> Body:
    """Read the body's lines as CommonMark renders them, and refuse a heading not `## Title`."""
    headings: list[Heading] = []
    visible: list[str] = []
    problems: list[str] = []
    fence: str | None = None
    previous: str | None = None
    offset = 0
    for number, line in enumerate(body.splitlines(keepends=True), first_line):
        text = line.rstrip("\n")
        opened = fence
        fence = _fence(text, fence)
        if opened is not None or fence is not None:
            visible.append(" " * len(text) + line[len(text) :])
            previous = None
            offset += len(line)
            continue
        visible.append(line)
        heading = HEADING.fullmatch(text)
        if heading and not CLOSING_HASHES.search(heading["title"]):
            headings.append(Heading(heading["title"], offset, offset + len(line)))
        elif heading or ATX.match(text, CONTAINERS.match(text).end()):
            problems.append(
                f"line {number}: {text.strip()!r} renders as a heading; a unit heading is "
                "`## Title` at the start of a line, with no closing #"
            )
        elif previous is not None and SETEXT.fullmatch(text):
            problems.append(
                f"line {number - 1}: {previous.strip()!r} over {text.strip()!r} renders as a "
                f"heading; write `## {previous.strip()}`, or leave a blank line above the rule"
            )
        previous = None if not text.strip() or ATX.match(text) else text
        offset += len(line)
    if fence is not None:
        problems.append("unclosed code fence swallows the headings after it")
    return Body(headings, "".join(visible), problems)
