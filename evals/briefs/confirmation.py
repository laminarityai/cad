"""Check a stored scorecard's basis against the signed brief store."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import pint

from cad.agent_checks.store import find
from cad.briefs import store
from cad.briefs.model import AgentLimit, Requirement, Target, deciding_check
from cad.briefs.store import BriefRefused, BriefState, Status
from cad.confirmations import agent_checks
from cad.projects.model import ProjectRefused
from cad.records.roots import Roots
from cad.records.signed import StoreUnusable
from cad.scorecard.model import (
    AgainstBrief,
    AgentChecked,
    AwaitingConfirmation,
    Checked,
    NoBrief,
    Scorecard,
    Unverified,
)
from cad.scorecard.requirements import (
    NoDecidingResult,
    assess_requirements,
    instance,
    labelled,
    result_of,
)
from cad.scorecard.unjudged import MeasureOnly, Reported
from cad.scorecard.waiting import Waiting

REFUSED: Final = (BriefRefused, ProjectRefused, StoreUnusable)
"""What the server raises when it refuses to read a brief's or project's stores."""


@dataclass(frozen=True, slots=True)
class Unconfirmed:
    reason: str


@dataclass(frozen=True, slots=True)
class Superseded:
    reason: str


@dataclass(frozen=True, slots=True)
class Misjudged:
    reason: str


type BasisFailure = Unconfirmed | Superseded | Misjudged


@dataclass(frozen=True, slots=True)
class Shown:
    requirements: tuple[Requirement, ...]


@dataclass(frozen=True, slots=True)
class BasisCheck:
    shown: Shown | None
    failures: tuple[BasisFailure, ...]


def check_basis(roots: Roots, card: Scorecard) -> BasisCheck:
    basis = card.basis
    match basis:
        case NoBrief():
            return BasisCheck(None, ())
        case AwaitingConfirmation():
            state = _state(roots, basis.brief_id)
            return BasisCheck(None, (state,) if isinstance(state, Unconfirmed) else ())
        case AgainstBrief():
            return _against(roots, card, basis)


def _against(roots: Roots, card: Scorecard, basis: AgainstBrief) -> BasisCheck:
    state = _state(roots, basis.brief_id)
    if isinstance(state, Unconfirmed):
        return BasisCheck(None, (state,))
    named = next(
        (
            one
            for one in state.proposals
            if one.status is Status.CONFIRMED
            and one.answered is not None
            and one.answered.sha256 == basis.decision_sha256
        ),
        None,
    )
    if named is None:
        return BasisCheck(
            None,
            (
                Unconfirmed(
                    f"brief {basis.brief_id} has no confirmation {basis.decision_sha256[:12]}"
                ),
            ),
        )
    shown = Shown(named.requirements)
    failures: list[BasisFailure] = []
    in_force = state.confirmed
    if in_force is not None and in_force is not named:
        failures.append(
            Superseded(
                f"scored against proposal {named.proposal.number}, "
                f"but proposal {in_force.proposal.number} is confirmed since"
            )
        )
    misjudged = _misjudged(roots, card, basis, shown)
    if misjudged is not None:
        failures.append(misjudged)
    return BasisCheck(shown, tuple(failures))


def _state(roots: Roots, brief_id: str) -> BriefState | Unconfirmed:
    try:
        return store.read_state(roots, brief_id)
    except REFUSED as error:
        return Unconfirmed(str(error))


def _misjudged(
    roots: Roots, card: Scorecard, basis: AgainstBrief, shown: Shown
) -> Misjudged | None:
    unjudged = _without_verdict(card, shown)
    if unjudged is not None:
        return unjudged
    try:
        derived = assess_requirements(
            basis.brief_id, basis.decision_sha256, shown.requirements, card.results
        )
    except (NoDecidingResult, pint.DimensionalityError) as error:
        return Misjudged(f"cannot judge the confirmed requirements: {error}")
    unapproved = _unapproved_agent_check(roots, basis, shown)
    if unapproved is not None:
        return unapproved
    mislabelled = _mislabelled(basis, shown)
    if mislabelled is not None:
        return mislabelled
    derived = _holding_agent_rows(derived, basis)
    if derived == basis:
        return None
    if len(derived.requirements) != len(basis.requirements):
        return Misjudged(
            f"the card judges {len(basis.requirements)} requirements, "
            f"and {len(derived.requirements)} were confirmed"
        )
    differs = next(
        held.requirement_id
        for held, again in zip(basis.requirements, derived.requirements, strict=True)
        if held != again
    )
    return Misjudged(f"requirement {differs} is not what its check results give")


def _without_verdict(card: Scorecard, shown: Shown) -> Misjudged | None:
    """The server shows a result that a confirmed target reads with its verdict."""
    results: Sequence[Reported] = card.results
    for requirement in shown.requirements:
        check_id = deciding_check(requirement.target)
        if check_id is None:
            continue
        if isinstance(result_of(results, check_id, instance(requirement.target)), MeasureOnly):
            return Misjudged(
                f"requirement {requirement.id} is confirmed, but the card shows its {check_id} "
                "result with no verdict"
            )
    return None


def _mislabelled(basis: AgainstBrief, shown: Shown) -> Misjudged | None:
    """A row carries the described label exactly when its confirmed load case is described."""
    targets: dict[str, Target] = {one.id: one.target for one in shown.requirements}
    for row in basis.requirements:
        if not isinstance(row, Checked | Waiting) or row.requirement_id not in targets:
            continue
        expected = labelled(targets[row.requirement_id])
        if row.load_case != expected:
            had = "no label" if row.load_case is None else "the described label"
            wanted = "none" if expected is None else "the described label"
            return Misjudged(
                f"requirement {row.requirement_id} carries {had}, and its confirmed load case "
                f"needs {wanted}"
            )
    return None


def _unapproved_agent_check(roots: Roots, basis: AgainstBrief, shown: Shown) -> Misjudged | None:
    """An agent-written check decides a requirement only when it is the one the confirmed
    agent_limit names and the person approved it on the confirmation page."""
    targets: dict[str, Target] = {one.id: one.target for one in shown.requirements}
    project = store.read_brief(roots, basis.brief_id).project
    for row in basis.requirements:
        if not isinstance(row, AgentChecked):
            continue
        target = targets.get(row.requirement_id)
        held = (
            find(roots.projects, project, target.check_sha256)
            if isinstance(target, AgentLimit)
            else None
        )
        if held is None or held.sha256 != row.check_sha256:
            return Misjudged(
                f"requirement {row.requirement_id} is decided by an agent-written check "
                "that its confirmed agent_limit does not name"
            )
        if agent_checks.outcome(roots, project, held) != "confirmed":
            return Misjudged(
                f"requirement {row.requirement_id} is decided by an agent-written check "
                "the person did not approve"
            )
    return None


def _holding_agent_rows(derived: AgainstBrief, basis: AgainstBrief) -> AgainstBrief:
    """`derived` leaves an approved agent-written check's requirement Unverified, because only the
    team results are on hand. Put the card's own row in its place, so the rest still compares."""
    held = {one.requirement_id: one for one in basis.requirements if isinstance(one, AgentChecked)}
    rows = tuple(
        held[one.requirement_id]
        if isinstance(one, Unverified) and one.requirement_id in held
        else one
        for one in derived.requirements
    )
    return AgainstBrief.model_validate(
        {
            **dict(derived),
            "requirements": rows,
            "unverified_requirements": tuple(
                one.requirement_id for one in rows if isinstance(one, Unverified)
            ),
            "agent_checked_requirements": tuple(
                one.requirement_id for one in rows if isinstance(one, AgentChecked)
            ),
        }
    )
