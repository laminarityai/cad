"""The signed brief store, and the only place that derives a status.

    <root>/<brief_id>/brief.signed
    <root>/<brief_id>/proposals/<n:04d>.signed
    <root>/<brief_id>/decisions/<n:04d>.signed     the person's answer to proposal n

Each `.signed` file is a `cad.records.signed` file whose slot is "<brief_id>/brief",
"<brief_id>/proposal/<n>" or "<brief_id>/decision/<n>", so a record moved to another slot or
another brief fails, and a second decision for one proposal loses to the first.
"""

import hashlib
import json
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

from cad.briefs.model import (
    Brief,
    BriefId,
    BriefSpan,
    Decision,
    Proposal,
    Requirement,
    RequirementId,
    Target,
)
from cad.projects.model import NewProjectId
from cad.records import signed
from cad.variants import key

BRIEFS_ROOT: Final = Path.home() / ".cad" / "briefs"
BRIEF: Final = "brief.signed"
PROPOSALS: Final = "proposals"
DECISIONS: Final = "decisions"
ID_PATTERN: Final = re.compile(r"[0-9a-f]{16}")
LOG = logging.getLogger(__name__)


class BriefRefused(Exception):
    """Agent-facing. The message names the brief id, never a host path."""


class UnknownBrief(BriefRefused):
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


@dataclass(frozen=True, slots=True)
class Draft:
    """A requirement before the store resolves its quote to a span and gives it an id."""

    target: Target
    quote: str


@dataclass(frozen=True, slots=True)
class ProposalState:
    proposal: Proposal
    sha256: str
    status: Status
    decision: Decision | None
    decision_sha256: str | None

    @property
    def requirement_ids(self) -> list[RequirementId]:
        return [r.id for r in self.proposal.requirements]


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


def parse_brief_id(raw: str) -> BriefId:
    if ID_PATTERN.fullmatch(raw) is None:
        raise UnknownBrief(f"a brief id is 16 lowercase hex digits, not {raw!r}")
    return BriefId(raw)


def create_brief(root: Path, text: str, project: NewProjectId) -> Brief:
    brief = Brief(
        id=BriefId(secrets.token_hex(8)),
        text=text,
        created_at=datetime.now(UTC),
        project_id=project,
    )
    first = (f"{brief.id}/brief", BRIEF, brief.model_dump_json().encode())
    if not signed.create_entry(_store(root), brief.id, first, (PROPOSALS, DECISIONS)):
        raise FileExistsError(f"brief {brief.id} already exists")
    return brief


def stored_briefs(root: Path) -> list[BriefId]:
    if not signed.is_directory(root):
        return []
    return [
        BriefId(path.name)
        for path in root.iterdir()
        if ID_PATTERN.fullmatch(path.name) and signed.is_directory(path)
    ]


def propose(root: Path, raw_id: str, drafts: Sequence[Draft]) -> ProposalState:
    """Store drafts as the next proposal, or return the latest when it is the same undecided set."""
    brief = read_state(root, raw_id).brief
    requirements = _resolve(brief, drafts)
    ids = [r.id for r in requirements]
    unchanged: ProposalState | None = None

    def next_proposal(existing: tuple[bytes, ...]) -> bytes | None:
        nonlocal unchanged
        latest = read_state(root, brief.id).latest
        if latest and latest.status is Status.PROPOSED and latest.requirement_ids == ids:
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
        return read_state(root, brief.id).proposals[stored.number - 1]
    if unchanged is None:
        raise TamperedBrief(_report(root, brief.id))
    return unchanged


def record_decision(root: Path, brief_id: BriefId, decision: Decision) -> Decision:
    """Store the person's answer for a proposal; if one is already stored, return that one.

    Only cad.briefs.page calls this, after a POST that spent a live ballot.
    """
    number = decision.proposal
    path = root / brief_id / DECISIONS / signed.slot_file(number)
    _publish(root, f"{brief_id}/decision/{number}", path, decision)
    stored = read_state(root, brief_id).proposal(number)
    if stored is None or stored.decision is None:
        raise TamperedBrief(f"{_report(root, brief_id)}: decision {number} did not persist")
    return stored.decision


def read_state(root: Path, raw_id: str) -> BriefState:
    """Read and verify every record of a brief and derive each proposal's status.

    A decided proposal is confirmed or declined. An undecided one is proposed when it is the
    newest and superseded otherwise. Any record that fails its MAC, its parse or its binding to
    the brief and proposal bytes raises TamperedBrief.
    """
    brief_id = parse_brief_id(raw_id)
    directory = root / brief_id
    if not signed.is_directory(directory):
        raise UnknownBrief(f"no brief {brief_id} is stored; store it with create_brief")
    brief_record = _read_signed(root, f"{brief_id}/brief", directory / BRIEF)
    brief = _parse(root, brief_id, Brief, brief_record)
    if brief.id != brief_id:
        raise TamperedBrief(_report(root, brief_id))
    proposals = _slots(root, brief_id, PROPOSALS)
    decisions = _slots(root, brief_id, DECISIONS)
    if list(proposals) != list(range(1, len(proposals) + 1)) or not set(decisions) <= set(
        proposals
    ):
        raise TamperedBrief(_report(root, brief_id))
    brief_sha256 = hashlib.sha256(brief_record).hexdigest()
    states: list[ProposalState] = []
    for number, path in proposals.items():
        record = _read_signed(root, f"{brief_id}/proposal/{number}", path)
        proposal = _parse(root, brief_id, Proposal, record)
        if proposal.number != number or not _belongs(proposal, brief):
            raise TamperedBrief(_report(root, brief_id))
        sha256 = hashlib.sha256(record).hexdigest()
        decision, decision_sha256 = None, None
        if number in decisions:
            decision_record = _read_signed(root, f"{brief_id}/decision/{number}", decisions[number])
            decision = _parse(root, brief_id, Decision, decision_record)
            if (decision.proposal, decision.brief_sha256, decision.proposal_sha256) != (
                number,
                brief_sha256,
                sha256,
            ):
                raise TamperedBrief(_report(root, brief_id))
            decision_sha256 = hashlib.sha256(decision_record).hexdigest()
        states.append(
            ProposalState(
                proposal=proposal,
                sha256=sha256,
                status=_status(decision, newest=number == len(proposals)),
                decision=decision,
                decision_sha256=decision_sha256,
            )
        )
    return BriefState(brief=brief, brief_sha256=brief_sha256, proposals=tuple(states))


def confirmed_requirements(root: Path, raw_id: str) -> ConfirmedSet | None:
    """The requirements checks read: the newest set a person confirmed, or None."""
    state = read_state(root, raw_id)
    confirmed = state.confirmed
    if confirmed is None or confirmed.decision_sha256 is None:
        return None
    return ConfirmedSet(
        brief_id=state.brief.id,
        proposal=confirmed.proposal.number,
        decision_sha256=confirmed.decision_sha256,
        requirements=confirmed.proposal.requirements,
        _seal=_SEAL,
    )


def _status(decision: Decision | None, *, newest: bool) -> Status:
    if decision is None:
        return Status.PROPOSED if newest else Status.SUPERSEDED
    return Status.CONFIRMED if decision.answer.verdict == "confirmed" else Status.DECLINED


def _resolve(brief: Brief, drafts: Sequence[Draft]) -> tuple[Requirement, ...]:
    requirements: list[Requirement] = []
    for index, draft in enumerate(drafts):
        start = brief.text.find(draft.quote) if draft.quote else -1
        if start < 0:
            raise BadProposal(
                f"requirements[{index}]: the quote does not appear in brief {brief.id}; "
                "copy the words exactly from the brief"
            )
        origin = BriefSpan(start=start, end=start + len(draft.quote))
        identity = json.dumps(
            [brief.id, draft.target.model_dump(mode="json"), origin.model_dump(mode="json")],
            sort_keys=True,
        )
        rid = RequirementId(hashlib.sha256(identity.encode()).hexdigest()[:16])
        if any(r.id == rid for r in requirements):
            raise BadProposal(f"requirements[{index}] repeats an earlier requirement")
        requirements.append(
            Requirement(id=rid, brief_id=brief.id, target=draft.target, origin=origin)
        )
    return tuple(requirements)


def _belongs(proposal: Proposal, brief: Brief) -> bool:
    return proposal.brief_id == brief.id and all(
        r.brief_id == brief.id and r.origin.end <= len(brief.text) for r in proposal.requirements
    )


def _read_signed(root: Path, slot: str, path: Path) -> bytes:
    record = signed.read(_store(root), slot, path)
    if record is None:
        raise TamperedBrief(_report(root, BriefId(slot.partition("/")[0])))
    return record


def _publish(root: Path, slot: str, path: Path, record: BaseModel) -> bool:
    return signed.publish(_store(root), slot, path, record.model_dump_json().encode())


def _parse[M: BaseModel](root: Path, brief_id: BriefId, model: type[M], record: bytes) -> M:
    try:
        return model.model_validate_json(record)
    except ValidationError as error:
        raise TamperedBrief(_report(root, brief_id)) from error


def _slots(root: Path, brief_id: BriefId, kind: str) -> dict[int, Path]:
    directory = root / brief_id / kind
    if not signed.is_directory(directory):
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
