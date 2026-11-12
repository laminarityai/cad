"""Read the pages cited by tables/materials.yaml and tables/fasteners.yaml and store the text that
carries the quotes.

    uv run python tools/regen_datasheet_text.py         refetch each url whose stored text is
                                                        missing or lacks a quote, delete files
                                                        no row cites
    uv run python tools/regen_datasheet_text.py --all   refetch every url, to see a datasheet
                                                        that changed

A page that is not PDF is read by the server's own fetch. A PDF is read by pypdf, then PDFium
(Chrome's PDF engine), then pdfminer, each only while a quote is still on no page. Exits 1 and
names each quote that is on no page of the datasheet.
"""

import io
import logging
import re
import subprocess
import sys
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass

import pypdfium2  # pyright: ignore[reportMissingTypeStubs]
from pdfminer.high_level import extract_text as miner_text
from pypdf import PdfReader

from cad.research.fetch import FetchFailed, fetch
from cad.tables.datasheet_text import (
    STORE,
    Citation,
    Extraction,
    citations,
    cover,
    fastener_citations,
    pages_of,
    render,
    text_path,
)
from cad.tables.fasteners import load_fasteners
from cad.tables.materials import load_materials

BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
)
TIMEOUT_SECONDS = 180
logging.disable(logging.WARNING)
INSIDE_ZIP = re.compile(r"\(([^()]+\.pdf) in the zip\)")


@dataclass(frozen=True, slots=True)
class Document:
    url: str
    title: str
    quotes: tuple[str, ...]


def documents(cited: Sequence[Citation]) -> list[Document]:
    urls = dict.fromkeys(citation.url for citation in cited)
    return [
        Document(
            url,
            next(c.title for c in cited if c.url == url),
            tuple(c.quote for c in cited if c.url == url),
        )
        for url in urls
    ]


def is_stored(document: Document) -> bool:
    path = text_path(document.url)
    if not path.exists():
        return False
    _, left = cover(document.quotes, [lambda: pages_of(path)])
    return not left


def download(url: str) -> bytes:
    """curl follows the certificate chains and non-ASCII urls that some datasheet hosts need."""
    command = ["curl", "-sSLf", "--max-time", str(TIMEOUT_SECONDS), "-A", BROWSER, url]
    return subprocess.run(command, capture_output=True, check=True).stdout


def pdf_of(document: Document, data: bytes) -> bytes:
    if data[:2] != b"PK":
        return data
    inside = INSIDE_ZIP.search(document.title)
    archive = zipfile.ZipFile(io.BytesIO(data))
    members = [name for name in archive.namelist() if inside and name.endswith(inside.group(1))]
    if not members:
        raise LookupError(f"the zip has no PDF named in the title; it has {archive.namelist()}")
    return archive.read(members[0])


def pdf_extractions(pdf: bytes) -> list[Extraction]:
    def pypdf() -> list[str]:
        return [page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages]

    def pdfium() -> list[str]:
        return [page.get_textpage().get_text_range() for page in pypdfium2.PdfDocument(pdf)]

    def pdfminer() -> list[str]:
        return miner_text(io.BytesIO(pdf)).split("\f")

    return [pypdf, pdfium, pdfminer]


def extractions_of(document: Document) -> list[Extraction] | str:
    data = download(document.url)
    if data[:2] == b"PK" or data.startswith(b"%PDF-"):
        return pdf_extractions(pdf_of(document, data))
    page = fetch(document.url)
    if isinstance(page, FetchFailed):
        return page.reason
    # A web page's text is mostly the whitespace of its markup; `on_page` ignores it.
    return [lambda: [" ".join(page.text.split())]]


def regenerate(document: Document) -> str | None:
    try:
        extractions = extractions_of(document)
    except (OSError, LookupError, ValueError, subprocess.CalledProcessError) as error:
        return f"could not read {document.url}: {type(error).__name__}: {error}"
    if isinstance(extractions, str):
        return extractions
    pages, left = cover(document.quotes, extractions)
    if left:
        return f"{document.url} has no page with the quote(s): " + "; ".join(map(repr, left))
    path = text_path(document.url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(document.url, pages), encoding="utf-8")
    return None


def main(argv: list[str]) -> int:
    everything = argv == ["--all"]
    if argv and not everything:
        print(__doc__)
        return 2
    wanted = documents([*citations(load_materials()), *fastener_citations(load_fasteners())])
    failures: list[str] = []
    for document in wanted:
        if not everything and is_stored(document):
            continue
        print(f"reading {document.url}", flush=True)
        if (failure := regenerate(document)) is not None:
            failures.append(failure)
    kept = {text_path(document.url) for document in wanted}
    for path in sorted(STORE.glob("*.txt")) if STORE.exists() else []:
        if path not in kept:
            print(f"deleting {path.name}, which no row cites")
            path.unlink()
    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
