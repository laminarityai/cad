from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NamedTuple

from pydantic import ValidationError

from cad.briefs.model import SAID_SEPARATOR, Brief, BriefId, Said
from cad.records import signed

SAID: Final = "said"


class Spoken(NamedTuple):
    transcript_seq: int | None
    text: str


@dataclass(frozen=True, slots=True)
class Words:
    newest_first: tuple[Spoken, ...] = ()
    refusal_hint: str = "copy the words exactly from the brief"


BRIEF_ONLY: Final = Words()


def joined(brief: Brief, said: Sequence[Said]) -> Brief:
    text = SAID_SEPARATOR.join((brief.text, *(s.text for s in said)))
    return brief.model_copy(update={"text": text})


def words_to_add(text: str, quotes: Sequence[str], words: Words) -> tuple[Spoken, ...]:
    found: list[Spoken] = []
    for quote in quotes:
        if not quote or quote in text or any(quote in one.text for one in found):
            continue
        match = next((one for one in words.newest_first if quote in one.text), None)
        if match is not None:
            found.append(match)
    return tuple(found)


def read(store: signed.Store, directory: Path, brief_id: BriefId) -> tuple[Said, ...] | None:
    if _stored_before_said(directory):
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


def append_unless_said(store: signed.Store, directory: Path, brief: Brief, spoken: Spoken) -> None:
    def record_for(existing: tuple[bytes, ...]) -> bytes | None:
        said = [Said.model_validate_json(record) for record in existing]
        if _already_said(brief, said, spoken):
            return None
        return (
            Said(
                brief_id=brief.id,
                number=len(existing) + 1,
                text=spoken.text,
                transcript_seq=spoken.transcript_seq,
                said_at=datetime.now(UTC),
            )
            .model_dump_json()
            .encode()
        )

    directory.mkdir(exist_ok=True)
    signed.append(store, directory, _slot(brief.id), record_for)


def _already_said(brief: Brief, said: Sequence[Said], spoken: Spoken) -> bool:
    if spoken.transcript_seq is None:
        return any(s.transcript_seq is None and s.text == spoken.text for s in said)
    return spoken.transcript_seq in {brief.transcript_seq, *(s.transcript_seq for s in said)}


def _stored_before_said(directory: Path) -> bool:
    try:
        directory.lstat()
    except FileNotFoundError:
        return True
    return False


def _slot(brief_id: BriefId) -> Callable[[int], str]:
    return lambda number: f"{brief_id}/said/{number}"
