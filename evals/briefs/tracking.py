"""The two SPEC.md tracking numbers: strict pass rate, and the share of requirements that a
reviewed check covers.

Scorecards carry no requirements yet. When PR 3 adds `Scorecard.requirements`, `outcomes_of` is the
one place to change: it turns a card's requirement results into `RequirementOutcome`s.
"""

from dataclasses import dataclass
from typing import Final

from cad.checks.result import Verdict
from cad.scorecard.model import Scorecard

NO_REQUIREMENTS: Final = "no requirements"


@dataclass(frozen=True, slots=True)
class RequirementOutcome:
    requirement_id: str
    verdict: Verdict
    reviewed: bool


@dataclass(frozen=True, slots=True)
class Ratio:
    numerator: int
    denominator: int


@dataclass(frozen=True, slots=True)
class NoRequirements:
    pass


type Share = Ratio | NoRequirements


@dataclass(frozen=True, slots=True)
class Tracking:
    strict_pass_rate: Share
    reviewed_coverage: Share


def outcomes_of(card: Scorecard) -> tuple[RequirementOutcome, ...]:
    # PR 3: read card.requirements, with reviewed set from the deciding check's review status.
    del card
    return ()


def track(outcomes: tuple[RequirementOutcome, ...]) -> Tracking:
    """A requirement passes strictly when a reviewed check decided it and the verdict is pass. An
    unverified requirement, or one an unreviewed check decided, counts against both numbers."""
    return Tracking(
        strict_pass_rate=_share(
            sum(1 for one in outcomes if one.reviewed and one.verdict == Verdict.PASS),
            len(outcomes),
        ),
        reviewed_coverage=_share(sum(1 for one in outcomes if one.reviewed), len(outcomes)),
    )


def describe(share: Share) -> str:
    if isinstance(share, NoRequirements):
        return NO_REQUIREMENTS
    return f"{share.numerator}/{share.denominator} ({share.numerator / share.denominator:.0%})"


def _share(numerator: int, denominator: int) -> Share:
    return Ratio(numerator, denominator) if denominator else NoRequirements()
