"""Check a stored scorecard's basis against the signed brief store.

A card scored against a brief names a decision. The card holds when that decision is a
confirmation the store can show, it is still the set in force, and judging the confirmed
requirements against the card's own results gives the card's basis again. Nothing on the card's
basis is trusted: it is re-derived.
"""

from dataclasses import dataclass
from pathlib import Path

import pint

from cad.briefs import store
from cad.briefs.model import Requirement
from cad.briefs.store import BriefRefused, BriefState, Status
from cad.records.signed import StoreUnusable
from cad.scorecard.model import AgainstBrief, AwaitingConfirmation, NoBrief, Scorecard
from cad.scorecard.requirements import NoDecidingResult, assess_requirements
from cad.variants import key


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


def check_basis(briefs_root: Path, card: Scorecard) -> BasisCheck:
    basis = card.basis
    match basis:
        case NoBrief():
            return BasisCheck(None, ())
        case AwaitingConfirmation():
            state = _state(briefs_root, basis.brief_id)
            if isinstance(state, Unconfirmed):
                return BasisCheck(None, (state,))
            if state.confirmed is not None:
                newer = state.confirmed.proposal.number
                return BasisCheck(None, (Superseded(f"proposal {newer} is confirmed since"),))
            return BasisCheck(None, ())
        case AgainstBrief():
            return _against(briefs_root, card, basis)


def _against(briefs_root: Path, card: Scorecard, basis: AgainstBrief) -> BasisCheck:
    state = _state(briefs_root, basis.brief_id)
    if isinstance(state, Unconfirmed):
        return BasisCheck(None, (state,))
    named = next(
        (
            one
            for one in state.proposals
            if one.status is Status.CONFIRMED and one.decision_sha256 == basis.decision_sha256
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
    shown = Shown(named.proposal.requirements)
    failures: list[BasisFailure] = []
    in_force = state.confirmed
    if in_force is not None and in_force.decision_sha256 != basis.decision_sha256:
        failures.append(
            Superseded(
                f"scored against proposal {named.proposal.number}, "
                f"but proposal {in_force.proposal.number} is confirmed since"
            )
        )
    misjudged = _misjudged(card, basis, shown)
    if misjudged is not None:
        failures.append(misjudged)
    return BasisCheck(shown, tuple(failures))


def _state(briefs_root: Path, brief_id: str) -> BriefState | Unconfirmed:
    if not key.key_path(briefs_root).is_file():
        return Unconfirmed(f"the brief store has no key at {key.key_path(briefs_root)}")
    try:
        return store.read_state(briefs_root, brief_id)
    except (BriefRefused, StoreUnusable) as error:
        return Unconfirmed(str(error))


def _misjudged(card: Scorecard, basis: AgainstBrief, shown: Shown) -> Misjudged | None:
    try:
        derived = assess_requirements(
            basis.brief_id, basis.decision_sha256, shown.requirements, card.results
        )
    except (NoDecidingResult, pint.DimensionalityError) as error:
        return Misjudged(f"cannot judge the confirmed requirements: {error}")
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
