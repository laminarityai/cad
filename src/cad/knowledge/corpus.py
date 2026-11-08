"""The knowledge corpus: Markdown files in git, one unit per `##` section.

A file starts with front matter that names its source, then sections:

    ---
    title: Water Density | U.S. Geological Survey
    url: https://example.com/page
    retrieved: 2026-11-07
    license: own-summary
    codes: [USGS]         (the material, part or standard codes the unit is about)
    mentions: [ABS]       (optional: codes the text names but the unit is not about)
    ---
    ## Density            -> id kb:<file stem>#density
    <!-- page: 2 -->      (optional; a number or a range)
    Our summary, with a verbatim quote in "double quotes" wherever a number is cited.

A query code (PLA+, M5x0.8) matches a unit only when it is one of the unit's declared codes, so a
unit that merely mentions PLA is not about PLA. A code-shaped or all-caps token in a unit's title,
heading or text must be under `codes:` (the unit is about it) or `mentions:` (the text names it
only to compare), or the file is refused. A title or heading naming a code that another unit
declares is refused the same way, in any letter case. Files are read as UTF-8, with a byte order
mark or Windows line endings accepted. A `##` line inside a fenced code block is text.

A number in a unit's text is never a value a check reads; checks read the tables by exact key.
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, cast

import yaml

from cad.knowledge.text import looks_like_a_code, normalize, tokens

CORPUS_PATH: Final = Path(__file__).resolve().parents[3] / "knowledge"
LICENSES: Final = frozenset({"own-summary", "apache-2.0", "cc-by-4.0", "mit"})
PAGE: Final = re.compile(r"<!--\s*page:\s*(?P<page>[^>]*?)\s*-->")
PAGE_VALUE: Final = re.compile(r"\d+(-\d+)?")
HEADING: Final = re.compile(r"## +(?P<title>.+?)\s*")
FENCE: Final = re.compile(r"\s*(```|~~~)")
FRONT_MATTER: Final = re.compile(r"\A---\n(?P<yaml>.*?)\n---\n", re.DOTALL)


class InvalidCorpus(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Pointer:
    id: str
    title: str
    url: str
    page: str | None
    section: str
    retrieved: date


@dataclass(frozen=True, slots=True)
class Unit:
    pointer: Pointer
    text: str
    codes: frozenset[str]
    mentions: frozenset[str]


@dataclass(frozen=True, slots=True)
class Corpus:
    version: str
    units: Mapping[str, Unit]


def load(path: Path = CORPUS_PATH) -> Corpus:
    """Read every `*.md` file, collect every problem, and raise InvalidCorpus listing them all."""
    files = sorted(path.glob("*.md"))
    problems: list[str] = [] if files else [f"{path.name}: no Markdown files"]
    problems.extend(
        f"{nested.relative_to(path)}: files in subdirectories are not read, move it up"
        for nested in sorted(path.glob("*/**/*.md"))
    )
    units: dict[str, Unit] = {}
    digest = hashlib.sha256()
    for file in files:
        data = file.read_bytes()
        digest.update(file.name.encode() + b"\0" + data + b"\0")
        try:
            text = data.decode("utf-8-sig").replace("\r\n", "\n")
        except UnicodeDecodeError as error:
            problems.append(f"{file.name}: not UTF-8 ({error.reason} at byte {error.start})")
            continue
        found, errors = _parse(file.stem, text)
        problems.extend(f"{file.name}: {error}" for error in errors)
        for unit in found:
            if unit.pointer.id in units:
                problems.append(f"{file.name}: duplicate unit {unit.pointer.id}")
            else:
                units[unit.pointer.id] = unit
    problems.extend(_undeclared_known_codes(units))
    if problems:
        raise InvalidCorpus("\n".join(problems))
    return Corpus(version=digest.hexdigest(), units=units)


def _undeclared_known_codes(units: Mapping[str, Unit]) -> list[str]:
    """A title or heading, in any case, that names a code another unit declares must declare it."""
    known = {code for unit in units.values() for code in unit.codes}
    return [
        f"{unit.pointer.id}: the title or heading names the known code {token!r}, "
        "declare it under codes: or mentions:"
        for unit in units.values()
        for token in tokens(f"{unit.pointer.title} {unit.pointer.section}")
        if token.casefold() in known and token.casefold() not in unit.codes | unit.mentions
    ]


@dataclass(frozen=True, slots=True)
class Source:
    title: str
    url: str
    retrieved: date
    codes: frozenset[str]
    mentions: frozenset[str]


def _parse(stem: str, text: str) -> tuple[list[Unit], list[str]]:
    match = FRONT_MATTER.match(text)
    if match is None:
        return [], ["no front matter"]
    try:
        meta: object = yaml.safe_load(match["yaml"])
    except yaml.YAMLError as error:
        return [], [f"front matter is not valid YAML: {str(error).splitlines()[0]}"]
    source, problems = _source(meta)
    if source is None:
        return [], problems
    body = text[match.end() :]
    headings = _headings(body)
    if not headings or body[: headings[0].start].strip():
        problems.append("text before the first ## heading")
    units: list[Unit] = []
    for heading, following in zip(headings, [*headings[1:], None], strict=False):
        end = following.start if following else len(body)
        unit = _unit(stem, source, heading.title, body[heading.end : end])
        if isinstance(unit, Unit):
            units.append(unit)
        else:
            problems.append(unit)
    return units, problems


@dataclass(frozen=True, slots=True)
class _Heading:
    title: str
    start: int
    end: int


def _headings(body: str) -> list[_Heading]:
    """Each `##` heading that is outside a fenced code block."""
    found: list[_Heading] = []
    fenced = False
    offset = 0
    for line in body.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        if FENCE.match(stripped):
            fenced = not fenced
        elif not fenced and (heading := HEADING.fullmatch(stripped)):
            found.append(_Heading(heading["title"], offset, offset + len(line)))
        offset += len(line)
    return found


def _source(meta: object) -> tuple[Source | None, list[str]]:
    if not isinstance(meta, dict):
        return None, ["front matter is not a mapping"]
    fields = cast(dict[str, object], meta)
    title, url, retrieved, license_ = (
        fields.get(k) for k in ("title", "url", "retrieved", "license")
    )
    problems: list[str] = []
    if not isinstance(title, str) or not title:
        problems.append("front matter needs a title")
    if not isinstance(url, str) or not url.startswith("https://"):
        problems.append("front matter needs an https:// url")
    if type(retrieved) is not date:
        problems.append("front matter retrieved must be a date such as 2026-11-07")
    if license_ not in LICENSES:
        problems.append(f"front matter license must be one of {sorted(LICENSES)}")
    codes, code_problems = _codes("codes", fields.get("codes", []))
    mentions, mention_problems = _codes("mentions", fields.get("mentions", []))
    problems.extend(code_problems + mention_problems)
    if problems or not (
        isinstance(title, str) and isinstance(url, str) and type(retrieved) is date
    ):
        return None, problems
    return Source(title, url, retrieved, codes, mentions), problems


def _codes(field: str, declared: object) -> tuple[frozenset[str], list[str]]:
    if not isinstance(declared, list):
        return frozenset(), [f"front matter {field} must be a list such as [PLA+]"]
    codes: set[str] = set()
    problems: list[str] = []
    for item in cast(list[object], declared):
        found = tokens(item) if isinstance(item, str) else []
        if len(found) != 1 or normalize(cast(str, item)).strip() != found[0]:
            problems.append(
                f"front matter {field} entry {item!r} must be one token such as PLA+ or M5x0.8"
            )
        else:
            codes.add(found[0].casefold())
    return frozenset(codes), problems


def _unit(stem: str, source: Source, section: str, text: str) -> Unit | str:
    page: str | None = None
    pages = list(PAGE.finditer(text))
    if len(pages) > 1:
        return f"section {section!r}: more than one page comment"
    if pages:
        found = pages[0]
        page = str(found["page"])
        if not PAGE_VALUE.fullmatch(page):
            return f"section {section!r}: page {page!r} is not a number or range"
        text = text[: found.start()] + text[found.end() :]
    text = text.strip()
    if not text:
        return f"section {section!r} is empty"
    slug = re.sub(r"[^a-z0-9]+", "-", section.casefold()).strip("-")
    if not slug:
        return f"section {section!r}: the heading has no letters or digits for an id"
    allowed = source.codes | source.mentions
    for token in tokens(f"{source.title} {section} {text}"):
        if looks_like_a_code(token) and token.casefold() not in allowed:
            return f"section {section!r}: names {token!r}, declare it under codes: or mentions:"
    pointer = Pointer(
        id=f"kb:{stem}#{slug}",
        title=source.title,
        url=source.url,
        page=page,
        section=section,
        retrieved=source.retrieved,
    )
    return Unit(pointer, text, source.codes, source.mentions)
