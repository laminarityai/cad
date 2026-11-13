"""A requirement's quote from a document the person added (ADR-0012)."""

from collections.abc import Callable
from pathlib import Path

from cad.briefs.model import Target
from cad.briefs.origins import FileQuote
from cad.briefs.store import Draft
from cad.projects.model import ProjectId
from cad.tables.quote import on_page
from cad.uploads import store, text
from cad.uploads.model import TEXT, BadUpload, Document


def draft(
    projects: Path,
    project: ProjectId,
    target: Target,
    quote: str,
    file_id: str,
    typed: Callable[[str], bool],
) -> Draft:
    """A requirement that quotes a document. The quote is found in the text of a Markdown or text
    file, or in the text stored for a PDF, as `on_page` matches a researched value's quote. An
    image, or a PDF with no text the reader can take, such as a scan, has no text to check, so its
    quote is kept as the agent read it, labelled. A withheld file is quoted only with words
    `typed` says the person typed, checked before the file is looked at so a refusal tells the
    agent nothing about it, and its text must be readable. Raises `SandboxUnavailable` when a PDF
    needs the reader and Docker or the reader image is missing."""
    found, data = store.document(projects, project, file_id)
    if found.withheld and not typed(quote):
        raise BadUpload(
            f"{found.name} is a standard the person kept from you: quote only words they typed "
            "in the brief or in a message of this conversation"
        )
    words = _text(projects, project, found, data)
    if words is None:
        if found.withheld:
            raise BadUpload(
                f"{found.name} holds no text the server can read, so it cannot check a quote"
            )
        cited = FileQuote(file_id=found.id, name=found.name, quote=quote, checked=False)
        return Draft(target=target, quote=quote, cited=cited)
    if not on_page(quote, words):
        raise BadUpload(f"the quote does not appear in {found.name}: copy its words exactly")
    cited = FileQuote(file_id=found.id, name=found.name, quote=quote, checked=True)
    return Draft(target=target, quote=quote, cited=cited, typed=found.withheld)


def _text(projects: Path, project: ProjectId, found: Document, data: bytes) -> str | None:
    if found.media_type in TEXT:
        return data.decode("utf-8")
    if found.media_type != "application/pdf":
        return None
    return text.pdf_text(projects, project, found, data)
