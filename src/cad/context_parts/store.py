import hashlib
import logging
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from cad.briefs import store as briefs
from cad.briefs.model import BriefSpan
from cad.confirmations.answers import Found, ItemRef, read_ledger
from cad.context_parts.ids import ContextPartId
from cad.context_parts.ingest import Facts, NotAPart
from cad.context_parts.model import ContextPartRecord, FromVariant, NewerRevision, Outcome
from cad.errors import Refused
from cad.projects.model import ProjectBusy, ProjectId, TamperedProject
from cad.records import key, signed
from cad.records.roots import Roots, project_store
from cad.sandbox import image
from cad.variant_sets import store as sets
from cad.variant_sets.model import Member, Revision
from cad.variants import entry

CONTEXT_PARTS: Final = "context_parts"
PARTS: Final = "parts"
LOG = logging.getLogger(__name__)

type Ingest = Callable[[bytes], Facts | NotAPart]


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
        return "waiting" if self.answer is None else self.answer.item.verdict

    @property
    def note(self) -> str:
        return self.answer.page.note if self.answer and self.outcome == "declined" else ""


class _Seal:
    pass


_SEAL: Final = _Seal()


@dataclass(frozen=True, slots=True)
class ConfirmedPart:
    number: int
    record: ContextPartRecord
    answer_sha256: str
    _seal: _Seal

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise TypeError("only cad.context_parts.store makes a ConfirmedPart")


def propose(
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
        return standing
    facts = ingest(held.brep)
    if isinstance(facts, NotAPart):
        raise BadContextPart(f"variant {held.id} cannot be a context part: {facts.reason}")
    _write_brep(projects / project / PARTS, held.brep, held.brep_sha256)
    record = ContextPartRecord(
        project=project,
        brief_id=brief.id,
        name=name,
        origin=BriefSpan(start=start, end=start + len(quote)),
        source=FromVariant(variant_id=held.id),
        brep_sha256=held.brep_sha256,
        facts=facts,
        proposed_at=datetime.now(UTC),
        replaces=_replaced(projects, project, parts, held.id),
    )
    directory = projects / project / CONTEXT_PARTS
    directory.mkdir(parents=True, exist_ok=True)
    found: list[Stored] = []

    def record_for(existing: tuple[bytes, ...]) -> bytes | None:
        found.clear()
        already = _newest_undeclined(_stored(projects, project, existing), held.brep_sha256)
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
    if not os.path.lexists(directory):
        return ()
    store = project_store(projects)
    readable = store.key_exists() or _left_by_crashed_first_proposal(directory)
    raw = signed.read_numbered(store, directory, _slot_of(project)) if readable else None
    if raw is None:
        raise TamperedProject(_report(projects, project))
    return _stored(projects, project, raw)


def newest_parts(projects: Path, project: ProjectId) -> tuple[Stored, ...]:
    return tuple({s.record.id: s for s in stored_parts(projects, project)}.values())


def confirmed_parts(projects: Path, project: ProjectId) -> tuple[ConfirmedPart, ...]:
    """The newest confirmed geometry of each part: an update still waiting is not measured."""
    confirmed = {
        s.record.id: ConfirmedPart(s.number, s.record, s.answer.sha256, _SEAL)
        for s in stored_parts(projects, project)
        if s.answer is not None and s.outcome == "confirmed"
    }
    return tuple(confirmed.values())


def fitted_by(projects: Path, project: ProjectId, brief_id: str) -> tuple[ConfirmedPart, ...]:
    """The confirmed parts a brief's design must fit: those proposed for that brief, so a part
    is never measured against the brief it was taken from."""
    return tuple(
        one for one in confirmed_parts(projects, project) if one.record.brief_id == brief_id
    )


def newer_revisions(projects: Path, project: ProjectId) -> dict[ContextPartId, NewerRevision]:
    """Each confirmed part whose slot now shows a newer revision than the one it came from."""
    tag = image.image_tag(image.BUILD)
    slots = sets.project_slots(projects, project)
    newer: dict[ContextPartId, NewerRevision] = {}
    for part in confirmed_parts(projects, project):
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
        replaced = [part for part in confirmed if part.record.source.variant_id in earlier]
        if replaced:
            return replaced[-1].record.id
    return None


def _current_confirmed(parts: tuple[Stored, ...], part: ContextPartId) -> Stored | None:
    confirmed = [one for one in parts if one.record.id == part and one.outcome == "confirmed"]
    return confirmed[-1] if confirmed else None


def _holds(member: Member, variant_id: str, tag: str) -> bool:
    return any(variant_id in _ids(one, tag) for one in member.revisions)


def _ids(revision: Revision, tag: str) -> set[str]:
    return {revision.built_as, revision.live_id(tag)}


def part_brep(projects: Path, part: ConfirmedPart) -> bytes:
    record = part.record
    path = projects / record.project / PARTS / f"{record.brep_sha256}.brep"
    data = signed.read_regular(path, entry.MAX_FILE_BYTES)
    if data is None or hashlib.sha256(data).hexdigest() != record.brep_sha256:
        LOG.error("%s is missing or does not match its SHA-256", path)
        raise TamperedProject(
            f"context part {record.id} of project {record.project} has lost its geometry; "
            "the operator must delete the project's context parts from the project store"
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


def _write_brep(directory: Path, brep: bytes, brep_sha256: str) -> None:
    path = directory / f"{brep_sha256}.brep"
    held = signed.read_regular(path, entry.MAX_FILE_BYTES)
    if held is not None and hashlib.sha256(held).hexdigest() == brep_sha256:
        return
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".pending-{secrets.token_hex(8)}"
    try:
        temporary.write_bytes(brep)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _left_by_crashed_first_proposal(directory: Path) -> bool:
    return signed.is_directory(directory) and all(
        path.name.startswith(".") for path in directory.iterdir()
    )


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
        f"project {project} has a context part this store did not sign or cannot read; "
        "the operator must delete the project's context parts from the project store"
    )
