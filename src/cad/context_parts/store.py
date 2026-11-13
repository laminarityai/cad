import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from cad.briefs import store as briefs
from cad.briefs.origins import BriefSpan
from cad.confirmations.answers import Found, ItemRef, read_ledger
from cad.context_parts.ids import ContextPartId
from cad.context_parts.ingest import Brep, Ingest, Ingested, NotAPart
from cad.context_parts.model import (
    ContextPartRecord,
    FromUpload,
    FromVariant,
    NewerRevision,
    Outcome,
)
from cad.errors import Refused
from cad.projects.model import ProjectBusy, ProjectId, TamperedProject
from cad.records import files, key, signed
from cad.records.roots import Roots, project_store
from cad.sandbox import image
from cad.variant_sets import store as sets
from cad.variant_sets.model import Member, Revision
from cad.variants import entry

CONTEXT_PARTS: Final = "context_parts"
PARTS: Final = "parts"
LOG = logging.getLogger(__name__)


class BadContextPart(Refused):
    pass


@dataclass(frozen=True, slots=True)
class Stored:
    number: int
    record: ContextPartRecord
    sha256: str
    answer: Found | None

    @property
    def ref(self) -> ItemRef:
        return _ref(self.record.project, self.number, self.sha256)

    @property
    def outcome(self) -> Outcome:
        """An upload is confirmed by the person who sent it, until they decline it."""
        if self.answer is not None:
            return self.answer.item.verdict
        return "confirmed" if isinstance(self.record.source, FromUpload) else "waiting"

    @property
    def note(self) -> str:
        return self.answer.page.note if self.answer and self.outcome == "declined" else ""


class _Seal:
    pass


_SEAL: Final = _Seal()


@dataclass(frozen=True, slots=True)
class ConfirmedPart:
    """`confirmation_sha256` is the SHA-256 of the page answer that confirmed the part, or of the
    upload's own record."""

    number: int
    record: ContextPartRecord
    confirmation_sha256: str
    _seal: _Seal

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise TypeError("only cad.context_parts.store makes a ConfirmedPart")


def propose_from_variant(
    roots: Roots,
    variants_root: Path,
    brief_id: str,
    quote: str,
    name: str,
    variant_id: str,
    ingest: Ingest,
) -> Stored:
    """Idempotent: the same BREP in the same project returns the stored record that is still
    waiting or confirmed. A part declined before gets a new record. A newer revision of the slot a
    confirmed part came from updates that part: the record keeps its id."""
    brief = briefs.read_brief(roots, brief_id)
    start = brief.text.find(quote) if quote else -1
    if start < 0:
        raise BadContextPart(
            f"the quote does not appear in brief {brief.id}; copy the words exactly from the brief"
        )
    held = entry.open_entry(variants_root, variant_id, image.image_tag(image.BUILD))
    projects, project = roots.projects, brief.project
    parts = stored_parts(projects, project)
    standing = _newest_undeclined(parts, held.brep_sha256)
    if standing is not None:
        write_content(brep_path(projects, project, held.brep_sha256), held.brep, held.brep_sha256)
        return standing
    read = ingest(Brep(held.brep))
    if isinstance(read, NotAPart):
        raise BadContextPart(f"variant {held.id} cannot be a context part: {read.reason}")
    write_content(brep_path(projects, project, held.brep_sha256), held.brep, held.brep_sha256)
    record = ContextPartRecord(
        project=project,
        brief_id=brief.id,
        name=name,
        origin=BriefSpan(start=start, end=start + len(quote)),
        source=FromVariant(variant_id=held.id),
        brep_sha256=held.brep_sha256,
        facts=read.facts,
        proposed_at=datetime.now(UTC),
        replaces=_replaced(projects, project, parts, held.id),
    )
    return _append(projects, record)


def add_upload(
    projects: Path, project: ProjectId, name: str, upload: FromUpload, read: Ingested
) -> Stored:
    """Stores a part the person sent. The record is their confirmation, so it never waits on the
    card. Idempotent like `propose_from_variant`: the same solids return the record that still
    stands, and solids declined before get a new record."""
    brep_sha256 = hashlib.sha256(read.brep).hexdigest()
    write_content(brep_path(projects, project, brep_sha256), read.brep, brep_sha256)
    standing = _newest_undeclined(stored_parts(projects, project), brep_sha256)
    if standing is not None:
        return standing
    record = ContextPartRecord(
        project=project,
        name=name,
        source=upload,
        brep_sha256=brep_sha256,
        facts=read.facts,
        proposed_at=datetime.now(UTC),
    )
    return _append(projects, record)


def _append(projects: Path, record: ContextPartRecord) -> Stored:
    project = record.project
    directory = projects / project / CONTEXT_PARTS
    found: list[Stored] = []

    def record_for(existing: tuple[bytes, ...]) -> bytes | None:
        found.clear()
        already = _newest_undeclined(_stored(projects, project, existing), record.brep_sha256)
        if already is not None:
            found.append(already)
            return None
        return record.model_dump_json().encode()

    try:
        appended = signed.append(project_store(projects), directory, _slot_of(project), record_for)
    except signed.Tampered as error:
        raise TamperedProject(_report(projects, project)) from error
    except signed.Contended as error:
        raise ProjectBusy(
            f"project {project} is being given a part concurrently; try again"
        ) from error
    if isinstance(appended, signed.Appended):
        return stored_parts(projects, project)[appended.number - 1]
    return found[0]


def stored_parts(projects: Path, project: ProjectId) -> tuple[Stored, ...]:
    directory = projects / project / CONTEXT_PARTS
    raw = signed.read_numbered(project_store(projects), directory, _slot_of(project))
    if raw is None:
        raise TamperedProject(_report(projects, project))
    return _stored(projects, project, raw)


def newest_parts(projects: Path, project: ProjectId) -> tuple[Stored, ...]:
    return tuple({s.record.id: s for s in stored_parts(projects, project)}.values())


def confirmed_parts(projects: Path, project: ProjectId) -> tuple[ConfirmedPart, ...]:
    """The newest confirmed geometry of each part: an update still waiting is not measured."""
    confirmed = {
        s.record.id: ConfirmedPart(
            s.number, s.record, s.sha256 if s.answer is None else s.answer.sha256, _SEAL
        )
        for s in stored_parts(projects, project)
        if s.outcome == "confirmed"
    }
    return tuple(confirmed.values())


def fit_targets(
    projects: Path, project: ProjectId, brief_id: str, named: frozenset[str]
) -> tuple[ConfirmedPart, ...]:
    """The confirmed parts a brief's design must fit (ADR-0012): those proposed for that brief,
    and those a confirmed requirement of the brief names. A part is never measured against the
    brief it was taken from unless the person confirmed a requirement that names it."""
    return tuple(
        one
        for one in confirmed_parts(projects, project)
        if one.record.brief_id == brief_id or one.record.id in named
    )


def newer_revisions(projects: Path, project: ProjectId) -> dict[ContextPartId, NewerRevision]:
    """Each confirmed part whose slot now shows a newer revision than the one it came from."""
    tag = image.image_tag(image.BUILD)
    slots = sets.project_slots(projects, project)
    newer: dict[ContextPartId, NewerRevision] = {}
    for part in confirmed_parts(projects, project):
        if not isinstance(part.record.source, FromVariant):
            continue
        source = part.record.source.variant_id
        for where, member in slots:
            if _holds(member, source, tag) and source not in _ids(member.latest, tag):
                newer[part.record.id] = NewerRevision(
                    brief_id=where.brief_id, slot=member.slot, variant_id=member.latest.live_id(tag)
                )
                break
    return newer


def out_of_date_in(
    projects: Path, project: ProjectId, brief_id: str, slot: int
) -> tuple[ContextPartId, ...]:
    """The confirmed parts that came from an earlier revision of this slot."""
    return tuple(
        part
        for part, newer in newer_revisions(projects, project).items()
        if (newer.brief_id, newer.slot) == (brief_id, slot)
    )


def _replaced(
    projects: Path, project: ProjectId, parts: tuple[Stored, ...], variant_id: str
) -> ContextPartId | None:
    """The confirmed part whose geometry the user confirmed last came from an earlier revision of
    the slot `variant_id` is in, counting from that variant's latest revision there."""
    tag = image.image_tag(image.BUILD)
    confirmed = [
        part
        for part in parts
        if part.outcome == "confirmed" and _current_confirmed(parts, part.record.id) is part
    ]
    for _, member in sets.project_slots(projects, project):
        at = [n for n, one in enumerate(member.revisions) if variant_id in _ids(one, tag)]
        if not at:
            continue
        earlier = {vid for one in member.revisions[: at[-1]] for vid in _ids(one, tag)} - {
            variant_id
        }
        replaced = [part for part in confirmed if variant_of(part.record) in earlier]
        if replaced:
            return replaced[-1].record.id
    return None


def variant_of(record: ContextPartRecord) -> str | None:
    return record.source.variant_id if isinstance(record.source, FromVariant) else None


def _current_confirmed(parts: tuple[Stored, ...], part: ContextPartId) -> Stored | None:
    confirmed = [one for one in parts if one.record.id == part and one.outcome == "confirmed"]
    return confirmed[-1] if confirmed else None


def _holds(member: Member, variant_id: str, tag: str) -> bool:
    return any(variant_id in _ids(one, tag) for one in member.revisions)


def _ids(revision: Revision, tag: str) -> set[str]:
    return {revision.built_as, revision.live_id(tag)}


def part_brep(projects: Path, part: ConfirmedPart) -> bytes:
    record = part.record
    path = brep_path(projects, record.project, record.brep_sha256)
    data = files.read_regular(path, entry.MAX_FILE_BYTES)
    if data is None or hashlib.sha256(data).hexdigest() != record.brep_sha256:
        LOG.error("%s is missing or does not match its SHA-256", path)
        source = variant_of(record)
        again = (
            "add its file again" if source is None else f"propose it again from variant {source}"
        )
        raise TamperedProject(
            f"context part {record.id} of project {record.project} has lost its geometry; {again}"
        )
    return data


def _stored(projects: Path, project: ProjectId, raw: tuple[bytes, ...]) -> tuple[Stored, ...]:
    try:
        records = [ContextPartRecord.model_validate_json(one) for one in raw]
    except ValidationError as error:
        raise TamperedProject(_report(projects, project)) from error
    if any(record.project != project for record in records):
        raise TamperedProject(_report(projects, project))
    ledger = read_ledger(projects, project)
    parts: list[Stored] = []
    for number, (record, one) in enumerate(zip(records, raw, strict=True), start=1):
        sha256 = hashlib.sha256(one).hexdigest()
        parts.append(Stored(number, record, sha256, ledger.of(_ref(project, number, sha256))))
    return tuple(parts)


def _newest_undeclined(parts: tuple[Stored, ...], brep_sha256: str) -> Stored | None:
    """The record of this geometry that still stands: not declined, and not passed by a later
    record of its part that waits or was confirmed."""
    same = [part for part in parts if part.record.brep_sha256 == brep_sha256]
    if not same or same[-1].outcome == "declined":
        return None
    current = _current(parts).get(same[-1].record.id)
    return same[-1] if current is None or current.number <= same[-1].number else None


def _current(parts: tuple[Stored, ...]) -> dict[ContextPartId, Stored]:
    """Each part's newest record that waits or was confirmed."""
    return {part.record.id: part for part in parts if part.outcome != "declined"}


def brep_path(projects: Path, project: ProjectId, brep_sha256: str) -> Path:
    return projects / project / PARTS / f"{brep_sha256}.brep"


def write_content(path: Path, data: bytes, sha256: str) -> None:
    """Content-addressed: the file is named by its SHA-256, so a file already there that matches
    is kept and anything else is replaced whole."""
    held = files.read_regular(path, entry.MAX_FILE_BYTES)
    if held is not None and hashlib.sha256(held).hexdigest() == sha256:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    files.replace(path, data)


def _ref(project: ProjectId, number: int, sha256: str) -> ItemRef:
    return ItemRef(kind="context_part", slot=_slot_of(project)(number), sha256=sha256)


def _slot_of(project: ProjectId) -> Callable[[int], str]:
    return lambda number: f"{project}/context_part/{number}"


def _report(projects: Path, project: ProjectId) -> str:
    LOG.error(
        "%s holds a context part that %s did not sign or that cannot be read",
        projects / project / CONTEXT_PARTS,
        key.key_path(projects),
    )
    return (
        f"project {project}'s context parts failed the server's integrity check, so the project "
        "cannot use them; start a new project and add its parts there"
    )
