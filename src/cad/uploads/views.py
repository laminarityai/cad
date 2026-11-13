from typing import Literal

from pydantic import BaseModel

from cad.context_parts.ingest import Facts
from cad.context_parts.model import FromUpload, FromVariant, Outcome
from cad.context_parts.store import Stored
from cad.uploads.model import Document, MediaType


class ContextPartView(BaseModel):
    """A part of the project. A variant proposed for a brief names both; the fitting variant is
    built in this part's frame, so `variant_id`'s mesh draws with it as it is. An upload names
    the file the person sent instead. `left_out` says how much of that file could not be read."""

    part_id: str
    name: str
    origin: Literal["variant", "upload"]
    brief_id: str | None
    variant_id: str | None
    file_name: str | None
    outcome: Outcome
    size_mm: tuple[float, float, float]
    solids: int
    holes: int
    left_out: str | None


class DocumentView(BaseModel):
    file_id: str
    name: str
    media_type: MediaType
    size: int
    withheld: bool


def part_view(part: Stored) -> ContextPartView:
    record = part.record
    source = record.source
    facts = record.facts
    low, high = facts.box_min, facts.box_max
    return ContextPartView(
        part_id=record.id,
        name=record.name,
        origin=source.kind,
        brief_id=record.brief_id,
        variant_id=source.variant_id if isinstance(source, FromVariant) else None,
        file_name=source.file_name if isinstance(source, FromUpload) else None,
        outcome=part.outcome,
        size_mm=(high[0] - low[0], high[1] - low[1], high[2] - low[2]),
        solids=facts.solids,
        holes=len(facts.holes),
        left_out=left_out(facts),
    )


def left_out(facts: Facts) -> str | None:
    dropped = facts.left_out
    if dropped is None or dropped.unreadable == 0:
        return None
    return f"{dropped.unreadable} of {dropped.bodies} bodies could not be read"


def document_view(document: Document) -> DocumentView:
    return DocumentView(
        file_id=document.id,
        name=document.name,
        media_type=document.media_type,
        size=document.size,
        withheld=document.withheld,
    )
