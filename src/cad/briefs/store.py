import hashlib
import logging
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ValidationError

from cad.briefs import carry, said
from cad.briefs.edits import apply_edits
from cad.briefs.model import (
    MAX_BRIEF_CHARS,
    SAID_SEPARATOR,
    Answer,
    Brief,
    BriefId,
    Confirmed,
    Decision,
    Declined,
    Proposal,
    Requirement,
    RequirementId,
    Target,
)
from cad.briefs.origins import BriefSpan, FileQuote
from cad.confirmations.answers import Edit, ItemRef, Ledger, read_ledger
from cad.errors import NotFound, Refused
from cad.projects.model import NewProjectId
from cad.records import files, key, signed
from cad.records.roots import Roots

BRIEF: Final = "brief.signed"
PROPOSALS: Final = "proposals"
DECISIONS: Final = "decisions"
ID_PATTERN: Final = re.compile(r"[0-9a-f]{16}")
LOG = logging.getLogger(__name__)


class BriefRefused(Refused):
    """Agent-facing. The message names the brief id, never a host path."""


class UnknownBrief(BriefRefused, NotFound):
    pass


class BadProposal(BriefRefused):
    pass


class TamperedBrief(BriefRefused):
    pass


class Status(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    SUPERSEDED = "superseded"


HOLDS_THE_SET: Final = (Status.PROPOSED, Status.CONFIRMED)


@dataclass(frozen=True, slots=True)
class Draft:
    """A requirement before the store gives it an id. `cited` is a quote from a document. `typed`
    says the quote must also be words the person typed, as every quote of the brief is."""

    target: Target
    quote: str
    cited: FileQuote | None = None
    typed: bool = False


@dataclass(frozen=True, slots=True)
class Answered:
    answer: Answer
    sha256: str
    edits: tuple[Edit, ...] = ()


@dataclass(frozen=True, slots=True)
class ProposalState:
    proposal: Proposal
    sha256: str
    status: Status
    answered: Answered | None
    requirements: tuple[Requirement, ...]
    """The proposal's requirements with the person's edits applied: what a confirmation means."""

    @property
    def requirement_ids(self) -> list[RequirementId]:
        return [r.id for r in self.requirements]

    @property
    def ref(self) -> ItemRef:
        return proposal_ref(self.proposal, self.sha256)


@dataclass(frozen=True, slots=True)
class BriefState:
    brief: Brief
    brief_sha256: str
    proposals: tuple[ProposalState, ...]

    @property
    def latest(self) -> ProposalState | None:
        return self.proposals[-1] if self.proposals else None

    @property
    def confirmed(self) -> ProposalState | None:
        """The newest confirmed proposal: what checks read until a newer one is confirmed."""
        found = [p for p in self.proposals if p.status is Status.CONFIRMED]
        return found[-1] if found else None

    def proposal(self, number: int) -> ProposalState | None:
        return self.proposals[number - 1] if 1 <= number <= len(self.proposals) else None


class _Seal:
    pass


_SEAL: Final = _Seal()


@dataclass(frozen=True, slots=True)
class ConfirmedSet:
    """Requirements a person confirmed. Only `confirmed_requirements` can make one."""

    brief_id: BriefId
    proposal: int
    decision_sha256: str
    requirements: tuple[Requirement, ...]
    _seal: _Seal

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise TypeError("only cad.briefs.store makes a ConfirmedSet")


def proposal_ref(proposal: Proposal, sha256: str) -> ItemRef:
    slot = f"{proposal.brief_id}/proposal/{proposal.number}"
    return ItemRef(kind="requirements", slot=slot, sha256=sha256)


def parse_brief_id(raw: str) -> BriefId:
    if ID_PATTERN.fullmatch(raw) is None:
        raise UnknownBrief(f"a brief id is 16 lowercase hex digits, not {raw!r}")
    return BriefId(raw)


def create_brief(
    roots: Roots, text: str, project: NewProjectId, seq: int | None = None, name: str | None = None
) -> Brief:
    brief = Brief(
        id=BriefId(secrets.token_hex(8)),
        text=text,
        created_at=datetime.now(UTC),
        project_id=project,
        transcript_seq=seq,
        name=name,
    )
    first = (f"{brief.id}/brief", BRIEF, brief.model_dump_json().encode())
    children = (PROPOSALS, DECISIONS, said.SAID)
    if not signed.create_entry(_store(roots.briefs), brief.id, first, children):
        raise FileExistsError(f"brief {brief.id} already exists")
    return brief


def propose(
    roots: Roots,
    raw_id: str,
    drafts: Sequence[Draft],
    words: said.Words = said.BRIEF_ONLY,
    remove: Sequence[str] = (),
) -> ProposalState:
    root = roots.briefs
    state = read_state(roots, raw_id)
    brief = _add_quoted(roots, state.brief, drafts, words)
    requirements = carry.next_set(state, brief, drafts, words, remove)
    if isinstance(requirements, str):
        raise BadProposal(requirements)
    ids = [r.id for r in requirements]
    unchanged: ProposalState | None = None

    def next_proposal(existing: tuple[bytes, ...]) -> bytes | None:
        nonlocal unchanged
        latest = read_state(roots, brief.id).latest
        if latest and latest.status in HOLDS_THE_SET and latest.requirement_ids == ids:
            unchanged = latest
            return None
        unchanged = None
        return (
            Proposal(
                brief_id=brief.id,
                number=len(existing) + 1,
                requirements=requirements,
                created_at=datetime.now(UTC),
            )
            .model_dump_json()
            .encode()
        )

    try:
        stored = signed.append(
            _store(root),
            root / brief.id / PROPOSALS,
            lambda number: f"{brief.id}/proposal/{number}",
            next_proposal,
        )
    except signed.Contended as error:
        raise BadProposal(
            f"brief {brief.id} is being proposed to concurrently; try again"
        ) from error
    except signed.Tampered as error:
        raise TamperedBrief(_report(root, brief.id)) from error
    if isinstance(stored, signed.Appended):
        return read_state(roots, brief.id).proposals[stored.number - 1]
    if unchanged is None:
        raise TamperedBrief(_report(root, brief.id))
    return unchanged


def _add_quoted(roots: Roots, brief: Brief, drafts: Sequence[Draft], words: said.Words) -> Brief:
    quotes = [d.quote for d in drafts if d.cited is None or d.typed]
    added = said.words_to_add(brief.text, quotes, words)
    grown = len(brief.text) + sum(len(SAID_SEPARATOR) + len(one.text) for one in added)
    if grown > MAX_BRIEF_CHARS:
        raise BadProposal(
            f"brief {brief.id} would pass {MAX_BRIEF_CHARS} characters: create a new brief"
        )
    directory = roots.briefs / brief.id / said.SAID
    try:
        for spoken in added:
            said.append_unless_said(_store(roots.briefs), directory, brief, spoken)
    except signed.Contended as error:
        raise BadProposal(f"brief {brief.id} is being added to concurrently; try again") from error
    except signed.Tampered as error:
        raise TamperedBrief(_report(roots.briefs, brief.id)) from error
    return read_brief(roots, brief.id) if added else brief


def read_brief(roots: Roots, raw_id: str) -> Brief:
    return _read_brief(roots.briefs, parse_brief_id(raw_id))[0]


def read_state(roots: Roots, raw_id: str) -> BriefState:
    root = roots.briefs
    brief, brief_sha256 = _read_brief(root, parse_brief_id(raw_id))
    proposals = _slots(root, brief.id, PROPOSALS)
    decisions = _slots(root, brief.id, DECISIONS)
    if list(proposals) != list(range(1, len(proposals) + 1)) or not set(decisions) <= set(
        proposals
    ):
        raise TamperedBrief(_report(root, brief.id))
    ledger: Ledger | None = None
    states: list[ProposalState] = []
    for number, path in proposals.items():
        record = _read_signed(root, f"{brief.id}/proposal/{number}", path)
        proposal = _parse(root, brief.id, Proposal, record)
        if proposal.number != number or not _belongs(proposal, brief):
            raise TamperedBrief(_report(root, brief.id))
        sha256 = hashlib.sha256(record).hexdigest()
        if number in decisions:
            answered = _legacy(root, brief.id, (number, brief_sha256, sha256), decisions[number])
        else:
            ledger = ledger or read_ledger(roots.projects, brief.project)
            answered = _on_page(ledger, proposal_ref(proposal, sha256))
        status = _status(answered, newest=number == len(proposals))
        edited = apply_edits(proposal.requirements, answered.edits if answered else ())
        if isinstance(edited, str):
            raise TamperedBrief(_report(root, brief.id))
        states.append(ProposalState(proposal, sha256, status, answered, edited))
    return BriefState(brief=brief, brief_sha256=brief_sha256, proposals=tuple(states))


def confirmed_requirements(roots: Roots, raw_id: str) -> ConfirmedSet | None:
    """The requirements checks read: the newest set a person confirmed, or None."""
    state = read_state(roots, raw_id)
    confirmed = state.confirmed
    if confirmed is None or confirmed.answered is None:
        return None
    return ConfirmedSet(
        brief_id=state.brief.id,
        proposal=confirmed.proposal.number,
        decision_sha256=confirmed.answered.sha256,
        requirements=confirmed.requirements,
        _seal=_SEAL,
    )


def _read_brief(root: Path, brief_id: BriefId) -> tuple[Brief, str]:
    directory = root / brief_id
    if not files.is_directory(directory):
        raise UnknownBrief(f"no brief {brief_id} is stored; store it with create_brief")
    record = _read_signed(root, f"{brief_id}/brief", directory / BRIEF)
    brief = _parse(root, brief_id, Brief, record)
    added = said.read(_store(root), directory / said.SAID, brief_id)
    if brief.id != brief_id or added is None:
        raise TamperedBrief(_report(root, brief_id))
    return said.joined(brief, added), hashlib.sha256(record).hexdigest()


def _legacy(root: Path, brief_id: BriefId, bound: tuple[int, str, str], path: Path) -> Answered:
    record = _read_signed(root, f"{brief_id}/decision/{bound[0]}", path)
    decision = _parse(root, brief_id, Decision, record)
    if (decision.proposal, decision.brief_sha256, decision.proposal_sha256) != bound:
        raise TamperedBrief(_report(root, brief_id))
    return Answered(decision.answer, hashlib.sha256(record).hexdigest())


def _on_page(ledger: Ledger, ref: ItemRef) -> Answered | None:
    found = ledger.of(ref)
    if found is None:
        return None
    if found.item.verdict == "confirmed":
        return Answered(Confirmed(), found.sha256, found.item.edits)
    return Answered(Declined(note=found.page.note), found.sha256)


def _status(answered: Answered | None, *, newest: bool) -> Status:
    if answered is None:
        return Status.PROPOSED if newest else Status.SUPERSEDED
    return Status.CONFIRMED if answered.answer.verdict == "confirmed" else Status.DECLINED


def _belongs(proposal: Proposal, brief: Brief) -> bool:
    return proposal.brief_id == brief.id and all(
        r.brief_id == brief.id
        and (not isinstance(r.origin, BriefSpan) or r.origin.end <= len(brief.text))
        for r in proposal.requirements
    )


def _read_signed(root: Path, slot: str, path: Path) -> bytes:
    record = signed.read(_store(root), slot, path)
    if record is None:
        raise TamperedBrief(_report(root, BriefId(slot.partition("/")[0])))
    return record


def _parse[M: BaseModel](root: Path, brief_id: BriefId, model: type[M], record: bytes) -> M:
    try:
        return model.model_validate_json(record)
    except ValidationError as error:
        raise TamperedBrief(_report(root, brief_id)) from error


def _slots(root: Path, brief_id: BriefId, kind: str) -> dict[int, Path]:
    directory = root / brief_id / kind
    if not files.is_directory(directory):
        raise TamperedBrief(_report(root, brief_id))
    found: dict[int, Path] = {}
    for path in directory.iterdir():
        if path.name.startswith("."):
            continue
        match = signed.SLOT_PATTERN.fullmatch(path.name)
        if match is None:
            raise TamperedBrief(_report(root, brief_id))
        found[int(match.group(1))] = path
    return dict(sorted(found.items()))


def _store(root: Path) -> signed.Store:
    return signed.Store(root, "brief")


def _report(root: Path, brief_id: BriefId) -> str:
    LOG.error(
        "%s holds a record that %s did not sign or that cannot be read",
        root / brief_id,
        key.key_path(root),
    )
    return (
        f"brief {brief_id} has a record this store did not sign or cannot read; "
        "the operator must delete the brief from the brief store"
    )
