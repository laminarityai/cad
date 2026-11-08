"""The knowledge corpus: Markdown files in git, one unit per `##` section.

A file starts with front matter that names its source, then sections:

    ---
    title: Water Density | U.S. Geological Survey
    url: https://example.com/page
    retrieved: 2026-11-07
    license: own-summary
    ---
    ## Density            -> id kb:<file stem>#density
    <!-- page: 2 -->      (optional; a number or a range)
    Our summary, with a verbatim quote in "double quotes" wherever a number is cited.

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

CORPUS_PATH: Final = Path(__file__).resolve().parents[3] / "knowledge"
LICENSES: Final = frozenset({"own-summary", "apache-2.0", "cc-by-4.0", "mit"})
PAGE: Final = re.compile(r"<!--\s*page:\s*(?P<page>[^>]*?)\s*-->")
PAGE_VALUE: Final = re.compile(r"\d+(-\d+)?")
HEADING: Final = re.compile(r"^## +(?P<title>.+?)\s*$", re.MULTILINE)
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


@dataclass(frozen=True, slots=True)
class Corpus:
    version: str
    units: Mapping[str, Unit]


def load(path: Path = CORPUS_PATH) -> Corpus:
    """Read every `*.md` file, collect every problem, and raise InvalidCorpus listing them all."""
    files = sorted(path.glob("*.md"))
    problems: list[str] = [] if files else [f"{path.name}: no Markdown files"]
    units: dict[str, Unit] = {}
    digest = hashlib.sha256()
    for file in files:
        data = file.read_bytes()
        digest.update(file.name.encode() + b"\0" + data + b"\0")
        found, errors = _parse(file.stem, data.decode())
        problems.extend(f"{file.name}: {error}" for error in errors)
        for unit in found:
            if unit.pointer.id in units:
                problems.append(f"{file.name}: duplicate unit {unit.pointer.id}")
            else:
                units[unit.pointer.id] = unit
    if problems:
        raise InvalidCorpus("\n".join(problems))
    return Corpus(version=digest.hexdigest(), units=units)


@dataclass(frozen=True, slots=True)
class Source:
    title: str
    url: str
    retrieved: date


def _parse(stem: str, text: str) -> tuple[list[Unit], list[str]]:
    match = FRONT_MATTER.match(text)
    if match is None:
        return [], ["no front matter"]
    source, problems = _source(yaml.safe_load(match["yaml"]))
    if source is None:
        return [], problems
    body = text[match.end() :]
    headings = list(HEADING.finditer(body))
    if not headings or body[: headings[0].start()].strip():
        problems.append("text before the first ## heading")
    units: list[Unit] = []
    for heading, following in zip(headings, [*headings[1:], None], strict=False):
        end = following.start() if following else len(body)
        unit = _unit(stem, source, heading["title"], body[heading.end() : end])
        if isinstance(unit, Unit):
            units.append(unit)
        else:
            problems.append(unit)
    return units, problems


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
    if not isinstance(retrieved, date):
        problems.append("front matter retrieved must be a date such as 2026-11-07")
    if license_ not in LICENSES:
        problems.append(f"front matter license must be one of {sorted(LICENSES)}")
    if problems or not (
        isinstance(title, str) and isinstance(url, str) and isinstance(retrieved, date)
    ):
        return None, problems
    return Source(title, url, retrieved), problems


def _unit(stem: str, source: Source, section: str, text: str) -> Unit | str:
    page: str | None = None
    found = PAGE.search(text)
    if found:
        page = str(found["page"])
        if not PAGE_VALUE.fullmatch(page):
            return f"section {section!r}: page {page!r} is not a number or range"
        text = text[: found.start()] + text[found.end() :]
    text = text.strip()
    if not text:
        return f"section {section!r} is empty"
    slug = re.sub(r"[^a-z0-9]+", "-", section.casefold()).strip("-")
    pointer = Pointer(
        id=f"kb:{stem}#{slug}",
        title=source.title,
        url=source.url,
        page=page,
        section=section,
        retrieved=source.retrieved,
    )
    return Unit(pointer, text)
