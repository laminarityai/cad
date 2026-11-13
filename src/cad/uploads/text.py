"""The text of a PDF a person added: taken once in the reader image and stored beside the file, so
a quote check reads it from the project instead of starting the reader again (ADR-0012)."""

import logging
from pathlib import Path
from typing import Final

from cad.projects.model import ProjectId
from cad.records import files
from cad.research.fetch import PdfFile, PdfText
from cad.research.pdf import MAX_CHARS, read_pdf
from cad.uploads.model import Document
from cad.uploads.store import SOURCES

SUFFIX: Final = ".text"
MAX_STORED_BYTES: Final = 4 * MAX_CHARS
LOG = logging.getLogger(__name__)


def pdf_text(projects: Path, project: ProjectId, found: Document, data: bytes) -> str | None:
    """The stored text of a PDF, read in the reader image and stored when the project has none:
    a file added before the text was stored gets it here, on first need. None when the reader
    could take no text, such as from a scan, or could not run. Raises `SandboxUnavailable` when
    Docker or the reader image is missing."""
    path = projects / project / SOURCES / f"{found.sha256}{SUFFIX}"
    held = files.read_regular(path, MAX_STORED_BYTES)
    if held is not None:
        try:
            return held.decode("utf-8")
        except UnicodeDecodeError:
            LOG.error("%s is not UTF-8 text, so the reader reads %s again", path, found.name)
    LOG.info("reading the text of %s in the reader image", found.id)
    read = read_pdf(PdfFile(found.name, data, found.sha256))
    if not isinstance(read, PdfText):
        return None
    text = "\n".join(read.pages)
    files.replace(path, text.encode("utf-8"))
    return text
