"""The knowledge corpus: Markdown files kept with the code, one unit per `##` section.

Each file is about one subject, named by its file stem: `polymaker-polyterra-pla.md` has
`subject: polymaker-polyterra-pla`. List the names that mean exactly that subject under
`aliases`. A search must name one of them, or it finds nothing; the section's names then choose
the unit.

    ---
    title: PolyTerra PLA+ technical data sheet V5.1 (Polymaker)
    url: https://example.com/page
    retrieved: 2026-11-07
    license: own-summary
    subject: polymaker-polyterra-pla-plus
    maker: Polymaker
    line: PolyTerra       (optional; a trademark product line)
    aliases: [PolyTerra PLA+, Polymaker PolyTerra PLA+]
    ---
    ## Density            -> id kb:<file stem>#density
    <!-- page: 2 -->      (optional; a number or a range)
    <!-- keys: densities, specific gravity -->   (optional; other names for this section)
    Our summary, with a verbatim quote in "double quotes" wherever a number is cited.

A variant is its own subject, and an alias belongs to one subject only: "PETG" is the alias of the
plain PETG subject, never of PETG HF. A file is either `family: true`, about a whole family, grade
or standard (PLA, 6061-T6, ISO 273), or branded. A branded file declares `maker:` and may declare
`line:`, and every alias must carry a word of one of them that is not a family word from
`cad.knowledge.families`. So "PLA" and "mild steel" are never one vendor's alias, because one
vendor's density is not the family's, and "British Steel" lends only "british". An alias of only
the maker's name and family words ("Bambu Lab", "Bambu PLA", "Bambu Lab filament") names a group
of the maker's products and is refused. A branded alias that is a run of words inside another
subject's alias ("Bambu PLA Basic" inside "Bambu PLA Basic Gradient") names a group that holds
the other product, so the loader refuses it and names both files, whichever file came first. A
family alias inside a longer one is the family by declaration, so "PLA" may sit inside
"PolyTerra PLA".

The corpus is reviewed like the tables, in pull requests. The loader catches the mistakes an
honest author makes and refuses names that become ambiguous across files. It does not check that
`maker:` or `line:` is true, just as the tables loader does not check that a density is:
`line: Matte` makes "PLA Matte" one vendor's alias. A false `line:` is a review error. Review
checklist: a `line:` that is a generic word (Matte, Pro, CF, HF, Basic) is a block.

A section's names are its heading and each comma-separated key in its `keys` comment. Each is
read like a query: cut into words, with the subject's own aliases and stopwords taken out, so
"## Pure water" in the water file answers to "pure". A query chooses a unit only when its other
words equal one of these names. Two sections of one file with an equal name, a key of only
stopwords or only the subject's name, a second keys comment, and a section with no name left are
refused.

The loader also refuses a file whose subject is not its stem, a duplicate YAML key, an alias that
is not a quoted string (`[6061]` is an int, `[NO]` a bool), an alias made only of stopwords, an
alias that two subjects claim, and a fenced code block that is never closed. Files are read as
UTF-8, with a byte order mark or Windows line endings accepted. A section starts only where a
reviewer sees a `## Title` heading in the rendered file (`cad.knowledge.markdown`); any other
heading form is refused with its line. A keys or page comment inside a code block is text.

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

from cad.knowledge.families import FAMILY_WORDS
from cad.knowledge.markdown import scan
from cad.knowledge.sections import Alias, Name, section_names
from cad.knowledge.text import STOPWORDS, tokens

CORPUS_PATH: Final = Path(__file__).resolve().parents[3] / "knowledge"
LICENSES: Final = frozenset({"own-summary", "apache-2.0", "cc-by-4.0", "mit"})
PAGE: Final = re.compile(r"<!--\s*page:\s*(?P<page>[^>]*?)\s*-->")
PAGE_VALUE: Final = re.compile(r"\d+(-\d+)?")
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
    text: str
    subject: str
    names: frozenset[Name]
    """The heading and each declared key (`cad.knowledge.sections`); a query names one."""


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
    family: bool


def _inside(short: Alias, long: Alias) -> bool:
    return any(long[i : i + len(short)] == short for i in range(len(long) - len(short) + 1))


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
    branded: set[Alias] = set()
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
            branded.update(() if source.family else source.aliases)
            for alias in source.aliases:
                if owners.setdefault(alias, source.subject) != source.subject:
                    problems.append(
                        f"{file.name}: alias {' '.join(alias)!r} is claimed by both "
                        f"{owners[alias]!r} and {source.subject!r}"
                    )
    problems.extend(
        f"{owners[short]}.md: alias {' '.join(short)!r} is inside {' '.join(long)!r} of "
        f"{owners[long]}.md, so it names a group, not one product; drop it or make it the "
        "full product name"
        for short in sorted(branded)
        for long in sorted(owners)
        if owners[short] != owners[long] and _inside(short, long)
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
    scanned = scan(body, first_line=text[: match.end()].count("\n") + 1)
    problems.extend(scanned.problems)
    headings = scanned.headings
    if not headings or body[: headings[0].start].strip():
        problems.append("text before the first ## heading")
    units: list[Unit] = []
    answers: dict[Name, str] = {}
    for heading, following in zip(headings, [*headings[1:], None], strict=False):
        span = slice(heading.end, following.start if following else len(body))
        unit = _unit(stem, source, heading.title, body[span], scanned.visible[span])
        if isinstance(unit, str):
            problems.append(unit)
            continue
        units.append(unit)
        for name in sorted(unit.names, key=sorted):
            other = answers.setdefault(name, unit.pointer.section)
            if other != unit.pointer.section:
                problems.append(
                    f"sections {other!r} and {unit.pointer.section!r} both answer to "
                    f"{' '.join(sorted(name))!r}; one query must choose one section"
                )
    return source, units, problems


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
    brand, brand_problems = _brand(fields)
    problems.extend(brand_problems)
    aliases, alias_problems = _aliases(fields.get("aliases"), brand)
    problems.extend(alias_problems)
    if problems or not (
        isinstance(title, str)
        and isinstance(url, str)
        and type(retrieved) is date
        and isinstance(subject, str)
    ):
        return None, problems
    return Source(title, url, retrieved, subject, aliases, brand is None), problems


@dataclass(frozen=True, slots=True)
class _Brand:
    words: frozenset[str]
    """Maker and line words that are not family words; an alias carries at least one."""
    maker: frozenset[str]
    """Every word of the maker's name; an alias of only these names the whole maker."""


def _brand(fields: dict[str, object]) -> tuple[_Brand | None, list[str]]:
    """What a branded file's aliases must carry, or None for a family file or a bad one."""
    family, maker, line = (fields.get(k) for k in ("family", "maker", "line"))
    if family is not None and type(family) is not bool:
        return None, ["front matter family must be true or false"]
    if family:
        if maker is None and line is None:
            return None, []
        return None, ["a family file has no maker or line; drop them or drop `family: true`"]
    problems: list[str] = []
    if not isinstance(maker, str) or not maker.strip():
        problems.append(
            "front matter needs a maker such as `maker: Polymaker`, "
            "or `family: true` when the source covers a whole family"
        )
    if line is not None and (not isinstance(line, str) or not line.strip()):
        problems.append("front matter line must be a product line name such as PolyTerra")
    if problems:
        return None, problems
    words = {
        word
        for word in tokens(f"{maker} {line or ''}")
        if word[0].isalnum() and word.casefold() not in FAMILY_WORDS and word not in STOPWORDS
    }
    if not words:
        return None, [f"front matter maker {maker!r} has no word of its own, only family words"]
    return _Brand(frozenset(words), frozenset(tokens(str(maker)))), []


def _aliases(declared: object, brand: _Brand | None) -> tuple[frozenset[Alias], list[str]]:
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
        elif brand is not None and brand.words.isdisjoint(words):
            problems.append(
                f"front matter aliases entry {item!r} has no word of the maker or line "
                f"({', '.join(sorted(brand.words))}); name the product as its maker sells it, "
                "or declare `family: true` when the source covers a whole family"
            )
        elif (
            brand is not None
            and {w for w in words if w not in STOPWORDS and w.casefold() not in FAMILY_WORDS}
            <= brand.maker
        ):
            problems.append(
                f"front matter aliases entry {item!r} is only the maker's name and family words, "
                "which names a group of the maker's products; add the product"
            )
        else:
            aliases.add(words)
    return frozenset(aliases), problems


def _unit(stem: str, source: Source, section: str, text: str, visible: str) -> Unit | str:
    """`visible` is `text` with code blocks blanked, so a comment inside one is not read."""
    page: str | None = None
    pages = list(PAGE.finditer(visible))
    if len(pages) > 1:
        return f"section {section!r}: more than one page comment"
    if pages:
        found = pages[0]
        page = str(found["page"])
        if not PAGE_VALUE.fullmatch(page):
            return f"section {section!r}: page {page!r} is not a number or range"
        text = text[: found.start()] + text[found.end() :]
        visible = visible[: found.start()] + visible[found.end() :]
    named = section_names(source.aliases, section, text, visible)
    if isinstance(named, str):
        return named
    names, text = named
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
    return Unit(pointer, text, source.subject, names)
