"""The two SPEC.md tracking numbers, strict pass rate and the share of requirements that a
reviewed check covers, and the lines counted apart beside them: who decided each verdict, and the
families of the requirements no check decides.
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, assert_never

from cad.checks.result import Verdict
from cad.scorecard.model import (
    AgainstBrief,
    AgentChecked,
    Checked,
    RequirementResult,
    Scorecard,
    Unverified,
)
from cad.scorecard.waiting import Waiting

NO_REQUIREMENTS: Final = "no requirements"


class By(StrEnum):
    """Who a requirement's verdict is by. ADR-0009 and ADR-0011 count each apart."""

    TEAM = "a team check on reviewed table values"
    RESEARCHED = "a team check on researched values"
    WAITING = "a team check that has not reported yet"
    AGENT_CHECK = "an agent-written check the person approved"
    NONE = "no check"


REVIEWED: Final = frozenset({By.TEAM, By.RESEARCHED})

FAMILIES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = tuple(
    (family, re.compile(pattern, re.IGNORECASE))
    for family, pattern in (
        ("holes and fasteners", r"\bholes?\b|bolt|screw|fasten|thread|tapped|\binserts?\b|\bM\d"),
        ("walls and thickness", r"\bwalls?\b|thick|\bfloor\b|\bshell\b"),
        ("printing and process", r"print|overhang|infill|layer|nozzle"),
        (
            "loads and stiffness",
            r"\bload|\bholds?\b|\bbear|strength|stiff|deflect|break|crack"
            r"|\d\s*(?:k?N|kg|lbf?)\b",
        ),
        ("fits and clearances", r"\bfits?\b|clearance|clamp|snap|press|slides?\b|mates?\b|gap"),
        ("sizes and shapes", r"\d\s*(?:mm|cm|in|inch|inches|\")|\blong|\bwide|\btall|diameter"),
    )
)
OTHER: Final = "other"


@dataclass(frozen=True, slots=True)
class RequirementOutcome:
    requirement_id: str
    verdict: Verdict
    by: By
    statement: str

    @property
    def reviewed(self) -> bool:
        return self.by in REVIEWED


@dataclass(frozen=True, slots=True)
class Ratio:
    numerator: int
    denominator: int


@dataclass(frozen=True, slots=True)
class NoRequirements:
    pass


type Share = Ratio | NoRequirements


@dataclass(frozen=True, slots=True)
class Decided:
    requirements: int
    passes: int


@dataclass(frozen=True, slots=True)
class Tracking:
    strict_pass_rate: Share
    reviewed_coverage: Share
    agent_coverage: Share
    by: Mapping[By, Decided]
    uncovered: Mapping[str, int]


def outcomes_of(card: Scorecard) -> tuple[RequirementOutcome, ...]:
    basis = card.basis
    if not isinstance(basis, AgainstBrief):
        return ()
    return tuple(
        RequirementOutcome(
            one.requirement_id,
            one.verdict if isinstance(one, Checked | AgentChecked) else Verdict.UNKNOWN,
            by_of(one),
            one.statement,
        )
        for one in basis.requirements
    )


def by_of(result: RequirementResult) -> By:
    match result:
        case Checked():
            return By.RESEARCHED if result.basis == "researched" else By.TEAM
        case Waiting():
            return By.WAITING
        case AgentChecked():
            return By.AGENT_CHECK
        case Unverified():
            return By.NONE
        case _:
            assert_never(result)


def family(statement: str) -> str:
    """A keyword family for a statement no check decides, for choosing which check to write next.
    The first family whose words appear wins. It is a reading aid and grades nothing."""
    return next((name for name, words in FAMILIES if words.search(statement)), OTHER)


def track(outcomes: tuple[RequirementOutcome, ...]) -> Tracking:
    """A requirement passes strictly when a reviewed check decided it and the verdict is pass. An
    unverified requirement, or one an unreviewed check decided, counts against both numbers."""
    return Tracking(
        strict_pass_rate=_share(
            sum(1 for one in outcomes if one.reviewed and one.verdict == Verdict.PASS),
            len(outcomes),
        ),
        reviewed_coverage=_share(sum(1 for one in outcomes if one.reviewed), len(outcomes)),
        agent_coverage=_share(
            sum(1 for one in outcomes if one.by is By.AGENT_CHECK), len(outcomes)
        ),
        by={
            by: Decided(
                sum(1 for one in outcomes if one.by is by),
                sum(1 for one in outcomes if one.by is by and one.verdict == Verdict.PASS),
            )
            for by in By
        },
        uncovered=dict(
            Counter(family(one.statement) for one in outcomes if one.by is By.NONE).most_common()
        ),
    )


def describe(share: Share) -> str:
    if isinstance(share, NoRequirements):
        return NO_REQUIREMENTS
    return f"{share.numerator}/{share.denominator} ({share.numerator / share.denominator:.0%})"


def describe_apart(tracking: Tracking) -> list[str]:
    lines = [
        f"requirements by {by}: {decided.requirements}, {decided.passes} passing"
        for by, decided in tracking.by.items()
    ]
    families = ", ".join(f"{name} {count}" for name, count in tracking.uncovered.items())
    lines.append(f"requirements no check decides, by keyword family: {families or 'none'}")
    return lines


def _share(numerator: int, denominator: int) -> Share:
    return Ratio(numerator, denominator) if denominator else NoRequirements()
