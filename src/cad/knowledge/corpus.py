"""The knowledge corpus: Markdown files kept with the code, one unit per `##` section.

Each file is about one subject, named by its file stem: `pla.md` has `subject: pla`. List the
names that mean exactly that subject under `aliases`. A search must name one of them, or it finds
nothing; the text then chooses the section.

    ---
    title: PolyTerra PLA+ technical data sheet V5.1 (Polymaker)
    url: https://example.com/page
    retrieved: 2026-11-07
    license: own-summary
    subject: pla-plus
    aliases: [PolyTerra PLA+, Polymaker PolyTerra PLA+]
    ---
    ## Density            -> id kb:<file stem>#density
    <!-- page: 2 -->      (optional; a number or a range)
    Our summary, with a verbatim quote in "double quotes" wherever a number is cited.

A variant is its own subject, and an alias belongs to one subject only: "PETG" is the alias of the
plain PETG subject, never of PETG HF. A branded product never claims the name of a whole family:
"PLA" is not an alias of PolyTerra PLA, because PolyTerra's density is not PLA's. The names in
`cad.knowledge.families` are refused as aliases unless the file declares `family: true`.

The loader refuses a file whose subject is not its stem, a duplicate YAML key, an alias that is
not a quoted string (`[6061]` is an int, `[NO]` a bool), an alias made only of stopwords, an alias
that two subjects claim, and a fenced code block that is never closed. Files are read as UTF-8,
with a byte order mark or Windows line endings accepted. A `##` line inside a fenced code block is
text, not a heading.

A number in a unit's text is never a value a check reads; checks read the tables by exact key.
"""

import hashlib
import re
from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final, cast

import yaml

from cad.knowledge.families import FAMILIES
from cad.knowledge.text import STOPWORDS, tokens

CORPUS_PATH: Final = Path(__file__).resolve().parents[3] / "knowledge"
LICENSES: Final = frozenset({"own-summary", "apache-2.0", "cc-by-4.0", "mit"})
PAGE: Final = re.compile(r"<!--\s*page:\s*(?P<page>[^>]*?)\s*-->")
PAGE_VALUE: Final = re.compile(r"\d+(-\d+)?")
HEADING: Final = re.compile(r"## +(?P<title>.+?)\s*")
FENCE: Final = re.compile(r"\s*(```|~~~)")
FRONT_MATTER: Final = re.compile(r"\A---\n(?P<yaml>.*?)\n---\n", re.DOTALL)
SUBJECT: Final = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")

type Alias = tuple[str, ...]


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
    text: str
    subject: str


@dataclass(frozen=True, slots=True)
class Corpus:
    version: str
    units: Mapping[str, Unit]
    aliases: Mapping[Alias, str]


@dataclass(frozen=True, slots=True)
class Source:
    title: str
    url: str
    retrieved: date
    subject: str
    aliases: frozenset[Alias]


def load(path: Path = CORPUS_PATH) -> Corpus:
    """Read every `*.md` file, collect every problem, and raise InvalidCorpus listing them all."""
    files = sorted(path.glob("*.md"))
    problems: list[str] = [] if files else [f"{path.name}: no Markdown files"]
    problems.extend(
        f"{nested.relative_to(path)}: files in subdirectories are not read, move it up"
        for nested in sorted(path.glob("*/**/*.md"))
    )
    units: dict[str, Unit] = {}
    owners: dict[Alias, str] = {}
    digest = hashlib.sha256()
    for file in files:
        data = file.read_bytes()
        digest.update(file.name.encode() + b"\0" + data + b"\0")
        try:
            text = data.decode("utf-8-sig").replace("\r\n", "\n")
        except UnicodeDecodeError as error:
            problems.append(f"{file.name}: not UTF-8 ({error.reason} at byte {error.start})")
            continue
        source, found, errors = _parse(file.stem, text)
        problems.extend(f"{file.name}: {error}" for error in errors)
        for unit in found:
            if unit.pointer.id in units:
                problems.append(f"{file.name}: duplicate unit {unit.pointer.id}")
            else:
                units[unit.pointer.id] = unit
        if source:
            for alias in source.aliases:
                if owners.setdefault(alias, source.subject) != source.subject:
                    problems.append(
                        f"{file.name}: alias {' '.join(alias)!r} is claimed by both "
                        f"{owners[alias]!r} and {source.subject!r}"
                    )
    if problems:
        raise InvalidCorpus("\n".join(problems))
    return Corpus(version=digest.hexdigest(), units=units, aliases=owners)


def _parse(stem: str, text: str) -> tuple[Source | None, list[Unit], list[str]]:
    match = FRONT_MATTER.match(text)
    if match is None:
        return None, [], ["no front matter"]
    try:
        meta: object = yaml.load(match["yaml"], _UniqueKeyLoader)
    except yaml.YAMLError as error:
        return None, [], [f"front matter is not valid YAML: {str(error).splitlines()[0]}"]
    source, problems = _source(stem, meta)
    if source is None:
        return None, [], problems
    body = text[match.end() :]
    headings, unclosed = _headings(body)
    if unclosed:
        problems.append("unclosed code fence swallows the headings after it")
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
    return source, units, problems


@dataclass(frozen=True, slots=True)
class _Heading:
    title: str
    start: int
    end: int


def _headings(body: str) -> tuple[list[_Heading], bool]:
    """Each `##` heading outside a fenced code block, and whether a fence is left open."""
    found: list[_Heading] = []
    fence: str | None = None
    offset = 0
    for line in body.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        marker = FENCE.match(stripped)
        if marker:
            fence = None if fence == marker[1] else (fence or marker[1])
        elif fence is None and (heading := HEADING.fullmatch(stripped)):
            found.append(_Heading(heading["title"], offset, offset + len(line)))
        offset += len(line)
    return found, fence is not None


def _source(stem: str, meta: object) -> tuple[Source | None, list[str]]:
    if not isinstance(meta, dict):
        return None, ["front matter is not a mapping"]
    fields = cast(dict[str, object], meta)
    title, url, retrieved, license_, subject = (
        fields.get(k) for k in ("title", "url", "retrieved", "license", "subject")
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
    if not isinstance(subject, str) or not SUBJECT.fullmatch(subject):
        problems.append("front matter needs a subject key such as pla-plus")
    elif subject != stem:
        problems.append(f"subject {subject!r} must be the file name {stem!r}, one file per subject")
    family = fields.get("family", False)
    if type(family) is not bool:
        problems.append("front matter family must be true or false")
    aliases, alias_problems = _aliases(fields.get("aliases"), family is True)
    problems.extend(alias_problems)
    if problems or not (
        isinstance(title, str)
        and isinstance(url, str)
        and type(retrieved) is date
        and isinstance(subject, str)
    ):
        return None, problems
    return Source(title, url, retrieved, subject, aliases), problems


def _aliases(declared: object, family: bool) -> tuple[frozenset[Alias], list[str]]:
    if not isinstance(declared, list) or not declared:
        return frozenset(), ["front matter needs aliases, a list of names such as [PolyTerra PLA+]"]
    aliases: set[Alias] = set()
    problems: list[str] = []
    for item in cast(list[object], declared):
        if not isinstance(item, str):
            problems.append(f"front matter aliases entry {item!r} is not a string, quote it")
            continue
        words = tokens(item)
        if not any(w[0].isalnum() for w in words):
            problems.append(f"front matter aliases entry {item!r} needs a letter or a digit")
        elif all(w in STOPWORDS for w in words):
            problems.append(f"front matter aliases entry {item!r} is only stopwords")
        elif words in FAMILIES and not family:
            problems.append(
                f"front matter aliases entry {item!r} names a whole family of material; "
                "name the product, or declare `family: true` if the source covers the family"
            )
        else:
            aliases.add(words)
    return frozenset(aliases), problems


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
    pointer = Pointer(
        id=f"kb:{stem}#{slug}",
        title=source.title,
        url=source.url,
        page=page,
        section=section,
        retrieved=source.retrieved,
    )
    return Unit(pointer, text, source.subject)
