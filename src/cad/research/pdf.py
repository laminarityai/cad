"""A PDF the server fetched is read in the reader image, a container with no network, never on
the host. The host bounds the bytes before it starts the reader and treats what the reader sends
as untrusted: it checks the report's shape and size, and strips control and bidirectional
characters from the text.

The reader image is defined here and not in `cad.sandbox.image`, because every file under
`src/cad/sandbox/` feeds every variant id and every check version. Its job is charged as a
`check`, as the export job is, because adding a kind would edit `cad.sandbox.meter`.
"""

import sys
import unicodedata
from pathlib import Path
from typing import Annotated, Final, Literal, TypedDict

from pydantic import Field, TypeAdapter, ValidationError

from cad.research.fetch import FetchFailed, Page, PdfFile, PdfText, fetch
from cad.sandbox import container, image
from cad.sandbox.container import Job, TooMuchOutput
from cad.sandbox.image import Image, find_image, image_tag
from cad.sandbox.outcome import SandboxUnavailable

READER: Final = Image(
    "cad-reader", image.SANDBOX_DIR / "reader", ("Dockerfile", "requirements.txt")
)
BUILD_IMAGE: Final = "uv run cad-reader build-image"
SCRIPT: Final = (Path(__file__).parent / "pdf_reader.py").read_text()
MAX_PAGES: Final = 200
MAX_CHARS: Final = 4_000_000
WALL_SECONDS: Final = 30
MEMORY_MB: Final = 512
TMPFS_MB: Final = 16
TITLE_CHARS: Final = 200
# Every format character (bidirectional marks and overrides, soft hyphens, zero-width joiners),
# every control character except line breaks and tabs, and every private or unassigned one.
# PDFium writes U+FFFE for a hyphen, and a Symbol font's glyphs, such as U+F0B4 for the times
# sign, as private ones.
_DROPPED: Final = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})
_KEPT: Final = frozenset("\n\t")


class _Read(TypedDict):
    kind: Literal["read"]
    title: str
    pages: list[str]


class _Locked(TypedDict):
    kind: Literal["refused"]
    why: Literal["password", "damaged"]


class _TooLarge(TypedDict):
    kind: Literal["refused"]
    why: Literal["too_many_pages", "too_much_text"]
    pages: int


_REPORT: Final = TypeAdapter[_Read | _Locked | _TooLarge](
    Annotated[_Read | _Locked | _TooLarge, Field(union_mode="left_to_right")]
)


def fetch_source(url: str) -> Page | PdfText | FetchFailed:
    fetched = fetch(url)
    return read_pdf(fetched) if isinstance(fetched, PdfFile) else fetched


def read_pdf(pdf: PdfFile) -> PdfText | FetchFailed:
    """Raises `SandboxUnavailable` when Docker or the reader image is missing, or the account's
    container-seconds are spent."""
    command = ("python", "-I", "-c", SCRIPT, str(MAX_PAGES), str(MAX_CHARS))
    job = Job("check", reader_image(), command, pdf.body, (), WALL_SECONDS, MEMORY_MB, TMPFS_MB)
    ran = container.run(job)
    seen = ran.attended
    if seen.killed_at_deadline:
        return _failed(pdf, f"the reader ran past its {WALL_SECONDS} s limit")
    if ran.state.OOMKilled:
        return _failed(pdf, f"the reader ran out of its {MEMORY_MB} MB")
    if isinstance(seen.report, TooMuchOutput) or ran.state.ExitCode != 0:
        return _failed(pdf, f"the reader stopped with exit code {ran.state.ExitCode}")
    try:
        report = _REPORT.validate_json(seen.report, strict=True)
    except ValidationError:
        return _failed(pdf, "the reader sent a malformed report")
    return _text(pdf, report)


def reader_image() -> str:
    tag = image_tag(READER)
    found = find_image(tag)
    if found is None:
        raise SandboxUnavailable(f"reader image {tag} is missing; run `{BUILD_IMAGE}`")
    return found


def _text(pdf: PdfFile, report: _Read | _Locked | _TooLarge) -> PdfText | FetchFailed:
    url = pdf.url
    match report:
        case {"why": "password"}:
            return FetchFailed(
                f"{url} is a PDF locked with a password, and the server reads only a PDF that "
                "opens without one; find another source"
            )
        case {"why": "damaged"}:
            return FetchFailed(
                f"{url} is a damaged PDF the reader cannot open; find another source"
            )
        case {"why": "too_many_pages", "pages": pages}:
            return FetchFailed(
                f"{url} is a PDF of {pages} pages, and the server reads at most {MAX_PAGES}; cite "
                "a shorter datasheet or a web page that states the value"
            )
        case {"why": "too_much_text"}:
            return FetchFailed(
                f"{url} holds more than {MAX_CHARS:,} characters of text, more than the server "
                "reads; cite a shorter datasheet or a web page that states the value"
            )
        case {"kind": "read", "title": title, "pages": pages}:
            if len(pages) > MAX_PAGES or sum(map(len, pages)) > MAX_CHARS:
                return _failed(pdf, "the reader sent more text than it was allowed")
            cleaned = tuple(clean(page) for page in pages)
            if not any(page.strip() for page in cleaned):
                return FetchFailed(
                    f"{url} is a PDF with no text layer, such as a scan, and the server does not "
                    "read images; find a PDF or web page whose text states the value"
                )
            heading = " ".join(clean(title).split())[:TITLE_CHARS]
            return PdfText(url, heading or url, cleaned, pdf.sha256)
        case _:
            return _failed(pdf, "the reader sent a malformed report")


def clean(text: str) -> str:
    """Each dropped character becomes a space, so "12", a times sign and "20" never read as
    1220. A space inside a word does not hide a quote, since `cad.tables.quote.on_page` joins
    letters."""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(
        one if one in _KEPT or unicodedata.category(one) not in _DROPPED else " " for one in unified
    )


def _failed(pdf: PdfFile, why: str) -> FetchFailed:
    return FetchFailed(
        f"the server could not read the PDF at {pdf.url}: {why}; find another source"
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["build-image"]:
        print("usage: cad-reader build-image")
        return 2
    try:
        print(image.build_image(READER))
    except SandboxUnavailable as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
