"""The signed brief store, and the only place that derives a status.

    <root>/<brief_id>/brief.signed
    <root>/<brief_id>/proposals/<n:04d>.signed
    <root>/<brief_id>/decisions/<n:04d>.signed     the person's answer to proposal n

A `.signed` file is a hex HMAC line, then the JSON record. The MAC covers a slot name such as
"<brief_id>/decision/3", so a record moved to another slot or another brief fails. Every write is
create-exclusive through `os.link`, so record and MAC land together and a second decision for one
proposal loses to the first.
"""

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import stat
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
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants import key

BRIEFS_ROOT: Final = Path.home() / ".cad" / "briefs"
BRIEF: Final = "brief.signed"
PROPOSALS: Final = "proposals"
DECISIONS: Final = "decisions"
ID_PATTERN: Final = re.compile(r"[0-9a-f]{16}")
SLOT_PATTERN: Final = re.compile(r"(\d{4})\.signed")
MAX_RECORD_BYTES: Final = 1024 * 1024
PROPOSE_ATTEMPTS: Final = 8
UNUSABLE: Final = "the brief store's key is unusable; the operator must fix it"
LOG = logging.getLogger(__name__)


class BriefRefused(Exception):
    """Agent-facing. The message names the brief id, never a host path."""


class UnknownBrief(BriefRefused):
    pass


class BadProposal(BriefRefused):
    pass


class TamperedBrief(BriefRefused):
    pass


class BriefStoreUnusable(Exception):
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


def create_brief(root: Path, text: str) -> Brief:
    brief = Brief(id=BriefId(secrets.token_hex(8)), text=text, created_at=_now())
    incoming = root / f".incoming-{secrets.token_hex(8)}"
    try:
        incoming.mkdir(parents=True)
        (incoming / PROPOSALS).mkdir()
        (incoming / DECISIONS).mkdir()
        record = brief.model_dump_json().encode()
        (incoming / BRIEF).write_bytes(_sign(root, f"{brief.id}/brief", record) + b"\n" + record)
        incoming.rename(root / brief.id)
    finally:
        shutil.rmtree(incoming, ignore_errors=True)
    return brief


def propose(root: Path, raw_id: str, drafts: Sequence[Draft]) -> ProposalState:
    """Store drafts as the next proposal, or return the latest when it is the same undecided set."""
    state = read_state(root, raw_id)
    requirements = _resolve(state.brief, drafts)
    for _ in range(PROPOSE_ATTEMPTS):
        latest = state.latest
        if (
            latest is not None
            and latest.status is Status.PROPOSED
            and _ids(latest.proposal.requirements) == _ids(requirements)
        ):
            return latest
        number = 1 if latest is None else latest.proposal.number + 1
        proposal = Proposal(
            brief_id=state.brief.id, number=number, requirements=requirements, created_at=_now()
        )
        path = root / state.brief.id / PROPOSALS / _slot(number)
        if _publish(root, f"{state.brief.id}/proposal/{number}", path, proposal):
            return read_state(root, state.brief.id).proposals[number - 1]
        state = read_state(root, state.brief.id)
    raise BadProposal(f"brief {state.brief.id} is being proposed to concurrently; try again")


def record_decision(root: Path, brief_id: BriefId, decision: Decision) -> Decision:
    """Store the person's answer for a proposal; if one is already stored, return that one.

    Only cad.briefs.page calls this, after a POST that spent a live ballot.
    """
    number = decision.proposal
    path = root / brief_id / DECISIONS / _slot(number)
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
    if not _is_directory(directory):
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


def _ids(requirements: Sequence[Requirement]) -> list[RequirementId]:
    return [r.id for r in requirements]


def _belongs(proposal: Proposal, brief: Brief) -> bool:
    return proposal.brief_id == brief.id and all(
        r.brief_id == brief.id and r.origin.end <= len(brief.text) for r in proposal.requirements
    )


def _publish(root: Path, slot: str, path: Path, record: BaseModel) -> bool:
    """Link the signed record into place. False when another writer already holds the slot."""
    data = record.model_dump_json().encode()
    signed = _sign(root, slot, data) + b"\n" + data
    temporary = path.parent.parent / f".pending-{secrets.token_hex(8)}"
    try:
        temporary.write_bytes(signed)
        os.link(temporary, path)
    except FileExistsError:
        return False
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _sign(root: Path, slot: str, record: bytes) -> bytes:
    try:
        return key.sign(root, slot, record)
    except SandboxUnavailable as error:
        raise BriefStoreUnusable(UNUSABLE) from error


def _read_signed(root: Path, slot: str, path: Path) -> bytes:
    brief_id = BriefId(slot.partition("/")[0])
    data = _read_regular(path)
    mac, newline, record = (data or b"").partition(b"\n")
    if not newline:
        raise TamperedBrief(_report(root, brief_id))
    try:
        signed = key.verify(root, slot, record, mac)
    except SandboxUnavailable as error:
        raise BriefStoreUnusable(UNUSABLE) from error
    if not signed:
        raise TamperedBrief(_report(root, brief_id))
    return record


def _parse[M: BaseModel](root: Path, brief_id: BriefId, model: type[M], record: bytes) -> M:
    try:
        return model.model_validate_json(record)
    except ValidationError as error:
        raise TamperedBrief(_report(root, brief_id)) from error


def _slots(root: Path, brief_id: BriefId, kind: str) -> dict[int, Path]:
    directory = root / brief_id / kind
    if not _is_directory(directory):
        raise TamperedBrief(_report(root, brief_id))
    found: dict[int, Path] = {}
    for path in directory.iterdir():
        if path.name.startswith("."):
            continue
        match = SLOT_PATTERN.fullmatch(path.name)
        if match is None:
            raise TamperedBrief(_report(root, brief_id))
        found[int(match.group(1))] = path
    return dict(sorted(found.items()))


def _slot(number: int) -> str:
    return f"{number:04d}.signed"


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


def _now() -> datetime:
    return datetime.now(UTC)


def _is_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _read_regular(path: Path) -> bytes | None:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            return None
        data = file.read(MAX_RECORD_BYTES + 1)
    return None if len(data) > MAX_RECORD_BYTES else data
