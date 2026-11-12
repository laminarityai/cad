"""A requirement's quote from a document the person added (ADR-0012)."""

from pathlib import Path

from cad.briefs.origins import FileQuote
from cad.projects.model import ProjectId
from cad.research.fetch import PdfFile, PdfText
from cad.research.pdf import read_pdf
from cad.tables.quote import on_page
from cad.uploads import store
from cad.uploads.model import TEXT, BadUpload, Document


def cited(projects: Path, project: ProjectId, file_id: str, quote: str) -> FileQuote:
    """Finds the quote in the text of a Markdown or text file, or in the text the reader image
    takes from a PDF, as `on_page` matches a researched value's quote. An image, or a PDF with
    no text the reader can take, such as a scan, has no text to check, so its quote is kept as
    the agent read it, labelled. Raises `SandboxUnavailable` when a PDF needs the reader and
    Docker or the reader image is missing."""
    found, data = store.document(projects, project, file_id)
    text = _text(found, data)
    if text is None:
        return FileQuote(file_id=found.id, name=found.name, quote=quote, checked=False)
    if not on_page(quote, text):
        raise BadUpload(f"the quote does not appear in {found.name}: copy its words exactly")
    return FileQuote(file_id=found.id, name=found.name, quote=quote, checked=True)


def _text(found: Document, data: bytes) -> str | None:
    if found.media_type in TEXT:
        return data.decode("utf-8")
    if found.media_type != "application/pdf":
        return None
    read = read_pdf(PdfFile(found.name, data, found.sha256))
    return "\n".join(read.pages) if isinstance(read, PdfText) else None
