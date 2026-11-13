"""What `check_models.py` runs: each TLC check, and the shape of a mutant it must catch."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    module: str
    config: str
    finding: str | None = None
    """The violation this check is known to find, named as TLC names it, or None to pass."""


JOB_LANES: Final = Check("JobLanes", "JobLanes.tla", "JobLanes.cfg")
JOB_LANES_CAP: Final = Check("JobLanesCap", "JobLanes.tla", "JobLanesCap.cfg")
JOB_LANES_STOP: Final = Check("JobLanesStop", "JobLanes.tla", "JobLanesStop.cfg")
ANSWERS: Final = Check("Answers", "Answers.tla", "Answers.cfg")
CARRY_ON: Final = Check("CarryOn", "CarryOn.tla", "CarryOn.cfg")
CARRY_ON_LIVE: Final = Check("CarryOnLive", "CarryOn.tla", "CarryOnLive.cfg")
AUTO_HOLD: Final = Check("AutoHold", "AutoHold.tla", "AutoHold.cfg")
CHECKS: Final = (
    JOB_LANES,
    JOB_LANES_CAP,
    JOB_LANES_STOP,
    Check("JobLanesTwoServers", "JobLanes.tla", "JobLanesTwoServers.cfg"),
    Check(
        "JobLanesTwoServersRefusal",
        "JobLanes.tla",
        "JobLanesTwoServersRefusal.cfg",
        finding="InterruptedMeansInterrupted",
    ),
    ANSWERS,
    Check("AnswersStale", "Answers.tla", "AnswersStale.cfg", finding="StaleWritesNothing"),
    CARRY_ON,
    CARRY_ON_LIVE,
    AUTO_HOLD,
)


@dataclass(frozen=True, slots=True)
class Mutant:
    name: str
    regression: str
    check: Check
    edits: tuple[tuple[str, str], ...]
    """(old, new) text replacements; each old text must occur exactly once in the model."""
    catches: str
