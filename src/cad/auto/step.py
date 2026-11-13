from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Final, assert_never

from cad.auto.model import (
    AccountLimit,
    AllPass,
    Asked,
    AutoState,
    Capped,
    Event,
    Mark,
    NeedsPerson,
    PersonStopped,
    Proposed,
    Revised,
    Running,
    Standing,
    Started,
    Stopped,
    StoppedByPerson,
    StopReason,
    TamperedRun,
    Tried,
    Unsettled,
)
from cad.checks.result import Verdict
from cad.scorecard.model import (
    AGENT_CHECK,
    AgainstBrief,
    AgentChecked,
    Checked,
    Scorecard,
    Unverified,
)
from cad.scorecard.requirements import UNCONFIRMED_PART, result_of
from cad.scorecard.waiting import Waiting

NO_STATEMENTS: Final[Mapping[str, str]] = MappingProxyType({})
PASSING: Final = frozenset(
    {Mark.PASS, Mark.PASS_RESEARCHED, Mark.PASS_AGENT_CHECK, Mark.UNVERIFIED}
)
DESCRIBED: Final = "a load case the agent described and the person confirmed"
WORDS: Final = {
    Mark.PASS: "passes",
    Mark.PASS_RESEARCHED: "passes on researched data",
    Mark.PASS_AGENT_CHECK: f"passes the {AGENT_CHECK}",
    Mark.FAIL: "fails",
    Mark.UNKNOWN: "unknown, and it is not a pass",
    Mark.UNVERIFIED: "not checked: no check covers it, so it is neither pass nor fail",
    Mark.AWAITS_PERSON: "waits on the person to confirm its context part",
}


def standing_of(card: Scorecard, revision: int, code_sha256: str) -> Standing | Unsettled:
    # card.not_verified holds agent measurements, so it is never read here.
    basis = card.basis
    if not isinstance(basis, AgainstBrief):
        raise ValueError("an auto run scores against its confirmed brief")
    if card.pending:
        return Unsettled()
    marks: list[tuple[str, Mark]] = []
    described: list[str] = []
    reasons: list[tuple[str, str]] = []
    for row in basis.requirements:
        match row:
            case Checked():
                marks.append((row.requirement_id, _mark(row)))
                if row.load_case == "described":
                    described.append(row.requirement_id)
                if row.verdict is not Verdict.PASS:
                    reasons.append((row.requirement_id, _why(card, row)))
            case Unverified():
                marks.append((row.requirement_id, Mark.UNVERIFIED))
            case AgentChecked():
                marks.append((row.requirement_id, _agent_mark(row)))
                if row.verdict is not Verdict.PASS:
                    reasons.append((row.requirement_id, row.reason))
            case Waiting():
                return Unsettled()
            case _:
                assert_never(row)
    return Standing(
        revision=revision,
        variant_id=card.variant_id,
        code_sha256=code_sha256,
        built=True,
        marks=tuple(marks),
        described=tuple(described),
        reasons=tuple(reasons),
    )


def _why(card: Scorecard, row: Checked) -> str:
    deciding = result_of(card.finished, row.check_id, row.instance)
    if deciding is None or deciding.verdict is Verdict.PASS:
        return row.reason
    return deciding.reason


def _mark(row: Checked) -> Mark:
    match row.verdict:
        case Verdict.PASS:
            return Mark.PASS_RESEARCHED if row.basis == "researched" else Mark.PASS
        case Verdict.FAIL:
            return Mark.FAIL
        case Verdict.UNKNOWN:
            return Mark.AWAITS_PERSON if row.reason == UNCONFIRMED_PART else Mark.UNKNOWN


def _agent_mark(row: AgentChecked) -> Mark:
    match row.verdict:
        case Verdict.PASS:
            return Mark.PASS_AGENT_CHECK
        case Verdict.FAIL:
            return Mark.FAIL
        case Verdict.UNKNOWN:
            return Mark.UNKNOWN


def fold(events: Sequence[Event]) -> AutoState:
    if not events or not isinstance(start := events[0], Started):
        raise TamperedRun("an auto run's log starts with its start record")
    state: AutoState = Running(start=start)
    if start.conflicts:
        ids = tuple(dict.fromkeys(rid for one in start.conflicts for rid in one.requirements))
        state = _stop(state, NeedsPerson(why="conflict", requirements=ids, bounds=start.conflicts))
    for event in events[1:]:
        state = step(state, event)
    return state


def step(state: AutoState, event: Event) -> AutoState:
    if isinstance(state, Stopped):
        return state
    match event:
        case Revised():
            return _revised(_counted(state, event.standing.code_sha256), event.standing)
        case Tried():
            return _counted(state, event.code_sha256)
        case Proposed():
            return _stop(
                state, NeedsPerson(why="proposes_requirements", requirements=event.requirements)
            )
        case Asked():
            return _stop(state, NeedsPerson(why="agent_asked", note=event.note))
        case Capped():
            return _stop(state, AccountLimit(refused=event.refused, reason=event.reason))
        case PersonStopped():
            return _stop(state, StoppedByPerson())
        case Started():
            raise TamperedRun("an auto run's log holds a second start record")
        case _:
            assert_never(event)


def _counted(state: Running, code_sha256: str) -> Running:
    if code_sha256 in state.builds:
        return state
    return state.model_copy(update={"builds": (*state.builds, code_sha256)})


def _revised(state: Running, standing: Standing) -> AutoState:
    state = state.model_copy(update={"history": (*state.history, standing)})
    waiting = tuple(rid for rid, mark in standing.marks if mark is Mark.AWAITS_PERSON)
    if waiting:
        return _stop(state, NeedsPerson(why="source_to_confirm", requirements=waiting))
    if standing.built and all(mark in PASSING for _, mark in standing.marks):
        return _stop(
            state,
            AllPass(
                researched=_ids(standing, Mark.PASS_RESEARCHED),
                agent_checked=_ids(standing, Mark.PASS_AGENT_CHECK),
                unverified=_ids(standing, Mark.UNVERIFIED),
                described=standing.described,
            ),
        )
    return state


def _ids(standing: Standing, mark: Mark) -> tuple[str, ...]:
    return tuple(rid for rid, one in standing.marks if one is mark)


def _stop(state: Running, reason: StopReason) -> Stopped:
    return Stopped(
        start=state.start,
        history=state.history,
        builds=state.builds,
        reason=reason,
        report=report(state.history, len(state.builds), reason),
    )


def report(
    history: tuple[Standing, ...],
    builds: int,
    reason: StopReason,
    said: Mapping[str, str] = NO_STATEMENTS,
    option: str | None = None,
) -> str:
    """The stop report. `builds` counts every build under the run. The agent's copy names ids.
    The person's passes `said`, each requirement's statement, and `option`, the name the latest
    checked variant has in its set."""

    def named(rids: Sequence[str]) -> str:
        return ", ".join(said.get(rid, rid) for rid in rids)

    lines = [
        _reason(reason, named),
        f"Builds tried: {builds}." if builds else "Nothing was built under the run.",
    ]
    if history:
        latest = history[-1]
        name = option or f"variant {latest.variant_id}"
        lines.append(
            f"The latest the run checked is {name}."
            if latest.built
            else "The latest the run checked did not build."
        )
        because = dict(latest.reasons)
        lines.extend(
            f"- {said.get(rid, f'requirement {rid}')}: {WORDS[mark]}{_because(because.get(rid))}"
            f"{_described(rid, latest)}"
            for rid, mark in latest.marks
        )
    return "\n".join(lines)


def _because(reason: str | None) -> str:
    return f": {reason}" if reason else ""


def _described(rid: str, standing: Standing) -> str:
    return f", on {DESCRIBED}" if rid in standing.described else ""


def _reason(reason: StopReason, named: Callable[[Sequence[str]], str]) -> str:
    match reason:
        case AllPass():
            line = "Every checked requirement passes."
            if reason.researched:
                line += f" These pass on researched data: {named(reason.researched)}."
            if reason.described:
                line += f" These pass on {DESCRIBED}: {named(reason.described)}."
            if reason.agent_checked:
                line += f" These pass an {AGENT_CHECK}: {named(reason.agent_checked)}."
            if reason.unverified:
                line += (
                    " No check covers these, so they count as neither pass nor fail: "
                    f"{named(reason.unverified)}."
                )
            return line
        case NeedsPerson():
            return _needs_person(reason, named(reason.requirements))
        case AccountLimit():
            return f"The account's usage limit refused a build under the run: {reason.reason}"
        case StoppedByPerson():
            return "The person stopped the run."
        case _:
            assert_never(reason)


def _needs_person(reason: NeedsPerson, ids: str) -> str:
    match reason.why:
        case "conflict":
            proofs = " ".join(f"{one.statement}." for one in reason.bounds)
            return f"The confirmed requirements conflict, so no variant was built. {proofs}"
        case "proposes_requirements" if not reason.requirements:
            return (
                "A change to the confirmed requirements was proposed, and only the person can "
                "confirm it."
            )
        case "proposes_requirements":
            return f"New requirements were proposed, and only the person can confirm them: {ids}."
        case "source_to_confirm":
            return f"These requirements wait on the person to confirm a context part: {ids}."
        case "agent_asked":
            return f"The agent asked for the person. Its note: {reason.note}"
