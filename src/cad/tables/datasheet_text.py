"""The stored text of every cited datasheet, and the check that each quote is in it.

`tables/datasheet_text/<sha>.txt` holds, for one cited url, the pages that carry its quotes, as
`tools/regen_datasheet_text.py` read them from the datasheet. The first line is `url: <url>`.
The rest is the pages, split by a form feed. A PDF has no one text, so a document holds the
pages of every extraction tool that was needed to put each quote on a page.

The check runs offline. A row's quote must be found, by the server's own `on_page`, on a page of
the stored text of the row's url, the row's number must be written in the quote, and so must the
row's unit, by its own spelling or one listed in `UNIT_SPELLINGS`, with case kept.
"""

import hashlib
import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final

import pint

from cad.research.quote import on_page
from cad.tables.fields import FIELDS
from cad.tables.materials import TABLE_PATH, UNITS, Known, MaterialsTable

STORE = TABLE_PATH.parent / "datasheet_text"
HEADER = "url: "
PAGE_BREAK = "\f"
REGEN = "uv run python tools/regen_datasheet_text.py"

NUMBER = re.compile(r"(?<![\d.,])\d+(?:[.,]\d+)*")
SPACE_GROUPED = re.compile(r"(?<![\d.,])\d{1,3}(?: \d{3})+(?![\d.,])")
POWER_OF_TEN = re.compile(r"(?<![\d.,])(\d+(?:\.\d+)?) ?[x\u00d7] ?10(\d)(?![\d.,])")

UNIT_SPELLINGS: Final = {
    "MPa": ("N/mm2",),
    "GPa": ("Gpa",),
    "ksi": (),
    "g/cm^3": ("g/cm3",),
    "kg/m^3": ("kg/m3",),
    "Mg/m^3": ("Mg/m3",),
    "lb/in^3": ("lbs/in.3",),
}

type Extraction = Callable[[], Sequence[str]]


@dataclass(frozen=True, slots=True)
class Citation:
    key: str
    field: str
    url: str
    title: str
    quote: str
    value: Decimal
    unit: pint.Unit


def text_path(url: str, store: Path = STORE) -> Path:
    return store / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.txt"


def render(url: str, pages: Iterable[str]) -> str:
    return f"{HEADER}{url}\n{PAGE_BREAK.join(pages)}"


def pages_of(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").partition("\n")[2].split(PAGE_BREAK)


def cover(quotes: Iterable[str], extractions: Iterable[Extraction]) -> tuple[list[str], list[str]]:
    """The pages that carry the quotes, and the quotes that no page of any extraction carries.
    An extraction runs only while a quote is still uncovered."""
    left = list(dict.fromkeys(quotes))
    kept: list[str] = []
    for extract in extractions:
        if not left:
            break
        pages = extract()
        found = {quote: [page for page in pages if on_page(quote, page)] for quote in left}
        for page in pages:
            if any(page in hits for hits in found.values()) and page not in kept:
                kept.append(page)
        left = [quote for quote in left if not found[quote]]
    return kept, left


def citations(table: MaterialsTable) -> Iterator[Citation]:
    for material in table.materials.values():
        for field in FIELDS:
            value = material.value(field)
            if isinstance(value, Known):
                source = value.source
                number = str(value.quantity.magnitude)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                unit = value.quantity.units  # pyright: ignore[reportUnknownMemberType]
                yield Citation(
                    material.key,
                    field,
                    source.url,
                    source.title,
                    source.quote,
                    Decimal(number),
                    unit,  # pyright: ignore[reportUnknownArgumentType]
                )


def written_in(value: Decimal, quote: str) -> bool:
    """Whether some number in the quote, read with "." or "," as its decimal mark or as digit
    grouping, equals `value`: 1.24 is written in "1,24 g/cm3" and 8960 in "8 960 kg/m3".
    "193 x 103" is 193000, never 193 or 103: a PDF text layer drops the raise of 10³.

    The power-of-ten reading also matches a dimension such as "3 x 104 mm", which reads as 30000.
    No current row is affected, and the quote check alone does not catch it."""
    return any(reading == value for reading in _readings(_fold(quote)))


def unit_written_in(unit: pint.Unit, quote: str) -> bool:
    """Whether the quote writes `unit`, by the spelling the table uses or one listed with it, on
    word boundaries and with case kept: MPa is not written in "mPa" and g/cm^3 is written in
    "g/cm³". A dimensionless value needs no unit.

    The check cannot tell which unit belongs to which number. A quote that prints two units, as
    "ksi. (MPa) 28.0 x 103 (193 x 103)" does, passes a row that pairs either number with either
    unit: 28000 MPa passes as well as 193000 MPa. Only the plausibility ranges in
    `cad.tables.materials` and a reviewer catch that switch."""
    if unit.dimensionless:
        return True
    text = _fold(quote)
    return any(
        re.search(rf"(?<![A-Za-z]){re.escape(spelling)}(?![A-Za-z0-9])", text)
        for name, others in UNIT_SPELLINGS.items()
        if UNITS.Unit(name) == unit
        for spelling in (name, *others)
    )


def _readings(quote: str) -> Iterator[Decimal]:
    for mantissa, exponent in POWER_OF_TEN.findall(quote):
        yield Decimal(mantissa).scaleb(int(exponent))
    quote = POWER_OF_TEN.sub(" ", quote)
    for token in NUMBER.findall(quote):
        head, *rest = re.split(r"[.,]", token)
        if not rest:
            yield Decimal(head)
        if rest and all(len(group) == 3 for group in rest):
            yield Decimal(head + "".join(rest))
        if rest and all(len(group) == 3 for group in rest[:-1]):
            yield Decimal(head + "".join(rest[:-1]) + "." + rest[-1])
    for token in SPACE_GROUPED.findall(quote):
        yield Decimal(token.replace(" ", ""))


def _fold(text: str) -> str:
    """NFKC with the minus sign as "-", and every run of whitespace as one space."""
    normal = unicodedata.normalize("NFKC", text).replace("\u2212", "-")
    return " ".join(normal.split())


def quote_problems(table: MaterialsTable, store: Path = STORE) -> list[str]:
    problems: list[str] = []
    cited: set[Path] = set()
    for citation in citations(table):
        path = text_path(citation.url, store)
        cited.add(path)
        if not path.exists():
            problems.append(
                f"{citation.key} {citation.field}: no stored text for {citation.url}."
                f" Run `{REGEN}` and commit the result."
            )
        elif not any(on_page(citation.quote, page) for page in pages_of(path)):
            problems.append(
                f"{citation.key} {citation.field}: the quote is not in the stored text of"
                f" {citation.url}: {citation.quote!r}. Run `{REGEN}`: it reads the datasheet again"
                " and fails if the quote is not in it word for word."
            )
        if not written_in(citation.value, citation.quote):
            problems.append(
                f"{citation.key} {citation.field}: {citation.value} is not written in its quote"
                f" {citation.quote!r}. Write the value as the quote prints it, in the quote's unit."
            )
        if not unit_written_in(citation.unit, citation.quote):
            problems.append(
                f"{citation.key} {citation.field}: its unit {citation.unit:~P} is not written in"
                f" its quote {citation.quote!r}. Quote the unit the sheet prints with the value,"
                " or write the value in the unit the quote prints."
            )
    problems.extend(
        f"{path.name}: no row cites its url. Run `{REGEN}` to delete it."
        for path in sorted(store.glob("*.txt"))
        if path not in cited
    )
    return problems
