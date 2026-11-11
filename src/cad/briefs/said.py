"""Words the person said after a brief was created: an append-only log beside its proposals.

A brief's text is its first words and then each Said, so a span into the text never moves. The
words a proposal quotes are added before the proposal, so a crash between the two leaves only the
person's words, which a retry finds already added.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from cad.briefs.model import SEPARATOR, Brief, BriefId, Said
from cad.records import signed

SAID: Final = "said"

type Spoken = tuple[int | None, str]
"""The person's words and the transcript seq they were copied from, None from an outside client."""


@dataclass(frozen=True, slots=True)
class Words:
    """Where a quote that is not in the brief yet may come from, newest first, and how to fix a
    quote that none of them holds."""

    candidates: tuple[Spoken, ...] = ()
    fix: str = "copy the words exactly from the brief"


BRIEF_ONLY: Final = Words()


def joined(brief: Brief, said: Sequence[Said]) -> Brief:
    return brief.model_copy(update={"text": SEPARATOR.join((brief.text, *(s.text for s in said)))})


def needed(text: str, quotes: Sequence[str], words: Words) -> tuple[Spoken, ...]:
    """The words to add so that each quote is in the text: for a quote the text lacks, the newest
    candidate that holds it."""
    found: list[Spoken] = []
    for quote in quotes:
        if not quote or quote in text or any(quote in held for _, held in found):
            continue
        match = next((one for one in words.candidates if quote in one[1]), None)
        if match is not None:
            found.append(match)
    return tuple(found)


def read(store: signed.Store, directory: Path, brief_id: BriefId) -> tuple[Said, ...] | None:
    """None when a record is not signed, not numbered in order, or another brief's. A brief stored
    before this log has no directory, and has no words after its first."""
    try:
        directory.lstat()
    except FileNotFoundError:
        return ()
    records = signed.read_numbered(store, directory, _slot(brief_id))
    if records is None:
        return None
    try:
        said = tuple(Said.model_validate_json(record) for record in records)
    except ValidationError:
        return None
    if any(s.number != n or s.brief_id != brief_id for n, s in enumerate(said, start=1)):
        return None
    return said


def append(store: signed.Store, directory: Path, brief: Brief, spoken: Spoken) -> None:
    """Add the words unless they are already the brief's: the same message, or the same text from
    an outside client. Raises what signed.append raises."""
    message, text = spoken

    def record_for(existing: tuple[bytes, ...]) -> bytes | None:
        said = [Said.model_validate_json(record) for record in existing]
        if message is not None and message in {brief.message, *(s.message for s in said)}:
            return None
        if message is None and any(s.message is None and s.text == text for s in said):
            return None
        return (
            Said(
                brief_id=brief.id,
                number=len(existing) + 1,
                text=text,
                message=message,
                said_at=datetime.now(UTC),
            )
            .model_dump_json()
            .encode()
        )

    directory.mkdir(exist_ok=True)
    signed.append(store, directory, _slot(brief.id), record_for)


def _slot(brief_id: BriefId) -> Callable[[int], str]:
    return lambda number: f"{brief_id}/said/{number}"
