"""The knowledge corpus: Markdown files kept with the code, one unit per `##` section.

Each file is one source about one subject, named by its file stem. `aliases` lists other names
for the subject; a search reads them, with the subject, as the unit's name.

    ---
    title: PolyTerra PLA+ technical data sheet V5.1 (Polymaker)
    url: https://example.com/page
    retrieved: 2026-11-07
    license: own-summary
    subject: polymaker-polyterra-pla-plus
    aliases: [PolyTerra PLA+, Polymaker PolyTerra PLA+]     (optional)
    ---
    ## Density            -> id kb:<file stem>#density
    <!-- page: 2 -->      (optional; a number or a range)
    <!-- keys: densities, specific gravity -->   (optional; other names for this section)
    Our summary, with a verbatim quote in "double quotes" wherever a number is cited.

The loader refuses malformed front matter (a missing or wrong field, an unknown or duplicate
key, an alias that is not a string), a subject that is not the file stem, a malformed page or
keys comment, and an empty or duplicate section. A section starts only where a reviewer sees a
`## Title` heading in the rendered file (`cad.knowledge.markdown`); any other heading form and
an unclosed code fence are refused with their line. A comment inside a code block is text.
Files are read as UTF-8, with a byte order mark or Windows line endings accepted.

A number in a unit's text is never a value a check reads; checks read the tables by exact key.
"""

import re
from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final, cast

import yaml

from cad.knowledge.markdown import scan

CORPUS_PATH: Final = Path(__file__).resolve().parents[3] / "knowledge"
LICENSES: Final = frozenset({"own-summary", "apache-2.0", "cc-by-4.0", "mit"})
FIELDS: Final = frozenset({"title", "url", "retrieved", "license", "subject", "aliases"})
PAGE: Final = re.compile(r"<!--\s*page:\s*(?P<page>[^>]*?)\s*-->")
PAGE_VALUE: Final = re.compile(r"\d+(-\d+)?")
KEYS: Final = re.compile(r"<!--\s*keys:\s*(?P<keys>[^>]*?)\s*-->")
KEYS_LIKE: Final = re.compile(r"<!--\s*keys", re.IGNORECASE)
FRONT_MATTER: Final = re.compile(r"\A---\n(?P<yaml>.*?)\n---\n", re.DOTALL)
SUBJECT: Final = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


class _UniqueKeyLoader(yaml.SafeLoader):
    """A safe YAML loader that refuses a mapping key written twice."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key: object = self.construct_object(key_node, deep=True)  # pyright: ignore[reportUnknownMemberType]
            if key in seen:
                raise yaml.YAMLError(f"duplicate key {key!r}")
            seen.add(key)
        return super().construct_mapping(node, deep)


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
    subject: str
    aliases: tuple[str, ...]
    keys: tuple[str, ...]
    text: str


@dataclass(frozen=True, slots=True)
class Corpus:
    units: Mapping[str, Unit]


@dataclass(frozen=True, slots=True)
class Source:
    title: str
    url: str
    retrieved: date
    subject: str
    aliases: tuple[str, ...]


def load(path: Path = CORPUS_PATH) -> Corpus:
    """Read every `*.md` file, collect every problem, and raise InvalidCorpus listing them all."""
    files = sorted(path.glob("*.md"))
    problems: list[str] = [] if files else [f"{path.name}: no Markdown files"]
    problems.extend(
        f"{nested.relative_to(path)}: files in subdirectories are not read, move it up"
        for nested in sorted(path.glob("*/**/*.md"))
    )
    units: dict[str, Unit] = {}
    for file in files:
        data = file.read_bytes()
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
    if problems:
        raise InvalidCorpus("\n".join(problems))
    return Corpus(units=units)


def _parse(stem: str, text: str) -> tuple[list[Unit], list[str]]:
    match = FRONT_MATTER.match(text)
    if match is None:
        return [], ["no front matter"]
    try:
        meta: object = yaml.load(match["yaml"], _UniqueKeyLoader)
    except yaml.MarkedYAMLError as error:
        return [], [f"front matter is not valid YAML{_where(error)}"]
    except yaml.YAMLError as error:
        return [], [f"front matter is not valid YAML: {str(error).splitlines()[0]}"]
    source, problems = _source(stem, meta)
    if source is None:
        return [], problems
    body = text[match.end() :]
    scanned = scan(body, first_line=text[: match.end()].count("\n") + 1)
    problems.extend(scanned.problems)
    headings = scanned.headings
    if not headings or body[: headings[0].start].strip():
        problems.append("text before the first ## heading")
    units: list[Unit] = []
    for heading, following in zip(headings, [*headings[1:], None], strict=False):
        span = slice(heading.end, following.start if following else len(body))
        unit = _unit(source, heading.title, body[span], scanned.visible[span])
        if isinstance(unit, str):
            problems.append(unit)
        else:
            units.append(unit)
    return units, problems


def _where(error: yaml.MarkedYAMLError) -> str:
    """The file's line and column of the problem. The front matter starts on line 2."""
    mark = error.problem_mark or error.context_mark
    said = error.problem or error.context or "a syntax error"
    if mark is None:
        return f": {said}"
    return f" at line {mark.line + 2}, column {mark.column + 1}: {said}"


def _source(stem: str, meta: object) -> tuple[Source | None, list[str]]:
    if not isinstance(meta, dict):
        return None, ["front matter is not a mapping"]
    fields = cast(dict[str, object], meta)
    title, url, retrieved, license_, subject = (
        fields.get(k) for k in ("title", "url", "retrieved", "license", "subject")
    )
    problems = [f"unknown front matter key {key!r}" for key in fields if key not in FIELDS]
    if not isinstance(title, str) or not title:
        problems.append("front matter needs a title")
    if not isinstance(url, str) or not url.startswith("https://"):
        problems.append("front matter needs an https:// url")
    if type(retrieved) is not date:
        problems.append("front matter retrieved must be a date such as 2026-11-07")
    if license_ not in LICENSES:
        problems.append(f"front matter license must be one of {sorted(LICENSES)}")
    if not isinstance(subject, str) or not SUBJECT.fullmatch(subject):
        problems.append("front matter needs a subject key such as pla-plus")
    elif subject != stem:
        problems.append(f"subject {subject!r} must be the file name {stem!r}, one file per subject")
    aliases = fields.get("aliases", [])
    if not isinstance(aliases, list):
        problems.append("front matter aliases must be a list of names such as [PolyTerra PLA+]")
        aliases = []
    problems.extend(
        f"front matter aliases entry {item!r} is not a string, quote it"
        for item in cast(list[object], aliases)
        if not isinstance(item, str)
    )
    if problems or not (
        isinstance(title, str)
        and isinstance(url, str)
        and type(retrieved) is date
        and isinstance(subject, str)
    ):
        return None, problems
    return Source(title, url, retrieved, subject, tuple(cast(list[str], aliases))), problems


def _cut(text: str, visible: str, found: list[re.Match[str]]) -> tuple[str, str]:
    """`text` and `visible` without the comments `found` in `visible`, offsets kept in step."""
    for match in reversed(found):
        text = text[: match.start()] + text[match.end() :]
        visible = visible[: match.start()] + visible[match.end() :]
    return text, visible


def _unit(source: Source, section: str, text: str, visible: str) -> Unit | str:
    """`visible` is `text` with code blocks blanked, so a comment inside one is not read."""
    pages = list(PAGE.finditer(visible))
    if len(pages) > 1:
        return f"section {section!r}: more than one page comment"
    page = pages[0]["page"] if pages else None
    if page is not None and not PAGE_VALUE.fullmatch(page):
        return f"section {section!r}: page {page!r} is not a number or range"
    text, visible = _cut(text, visible, pages)
    keys = list(KEYS.finditer(visible))
    if len(KEYS_LIKE.findall(visible)) != len(keys):
        return f"section {section!r}: a keys comment must read `<!-- keys: name, other name -->`"
    text, _ = _cut(text, visible, keys)
    text = text.strip()
    if not text:
        return f"section {section!r} is empty"
    slug = re.sub(r"[^a-z0-9]+", "-", section.casefold()).strip("-")
    if not slug:
        return f"section {section!r}: the heading has no letters or digits for an id"
    pointer = Pointer(
        id=f"kb:{source.subject}#{slug}",
        title=source.title,
        url=source.url,
        page=page,
        section=section,
        retrieved=source.retrieved,
    )
    names = tuple(name.strip() for match in keys for name in match["keys"].split(","))
    return Unit(pointer, source.subject, source.aliases, tuple(n for n in names if n), text)
