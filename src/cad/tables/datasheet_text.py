"""The stored text of every cited datasheet, and the check that each quote is in it.

`tables/datasheet_text/<sha>.txt` holds, for one cited url, the pages that carry its quotes, as
`tools/regen_datasheet_text.py` read them from the datasheet. The first line is `url: <url>`.
The rest is the pages, split by a form feed. A PDF has no one text, so a document holds the
pages of every extraction tool that was needed to put each quote on a page.

The check runs offline. A row's quote must be found, by the server's own `on_page`, on a page of
the stored text of the row's url.
"""

import hashlib
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from cad.research.submit import on_page
from cad.tables.materials import FIELD_UNITS, TABLE_PATH, Known, MaterialsTable

STORE = TABLE_PATH.parent / "datasheet_text"
HEADER = "url: "
PAGE_BREAK = "\f"
REGEN = "uv run python tools/regen_datasheet_text.py"

type Extraction = Callable[[], Sequence[str]]


@dataclass(frozen=True, slots=True)
class Citation:
    key: str
    field: str
    url: str
    title: str
    quote: str


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
        for field in FIELD_UNITS:
            value = material.value(field)
            if isinstance(value, Known):
                source = value.source
                yield Citation(material.key, field, source.url, source.title, source.quote)


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
    problems.extend(
        f"{path.name}: no row cites its url. Run `{REGEN}` to delete it."
        for path in sorted(store.glob("*.txt"))
        if path not in cited
    )
    return problems
