import statistics
from collections import Counter
from collections.abc import Sequence

from outcome import BriefResult, Counted, Frozen, Share, Trace
from readings import READ_AFTER
from tracking import By, Decided, apart


def pooled(shares: Sequence[Share]) -> Share:
    return Share(
        numerator=sum(one.numerator for one in shares),
        denominator=sum(one.denominator for one in shares),
    )


def percent(share: Share) -> str:
    if not share.denominator:
        return "no requirements"
    return f"{share.numerator}/{share.denominator} ({share.numerator / share.denominator:.0%})"


def _cards(counted: Counted) -> str:
    return (
        f"{counted.cards}, {counted.judged} judged, "
        f"{counted.resolved}/{counted.numbers} numbers resolved"
    )


def _pooled_counts(counts: Sequence[Counted]) -> Counted:
    return Counted(
        cards=sum(one.cards for one in counts),
        judged=sum(one.judged for one in counts),
        numbers=sum(one.numbers for one in counts),
        resolved=sum(one.resolved for one in counts),
    )


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def _row(one: BriefResult) -> str:
    trace = one.trace
    if one.status != "finished":
        verdict = f"SESSION FAILED: {one.note}"
    elif trace is None:
        verdict = f"not traced: {one.note}"
    else:
        verdict = "traced" if trace.traced else f"not traced ({len(trace.untraced)} untraced)"
    if trace is None:
        strict = coverage = "-"
    elif trace.failed:
        strict = coverage = "trace failed"
    else:
        strict, coverage = percent(trace.strict_pass), percent(trace.coverage)
    cost = "-" if one.cost_usd is None else f"${one.cost_usd:.2f}"
    return (
        f"| {one.id} | {one.domain} | {verdict} | {strict} | {coverage} "
        f"| {one.friction.confirmation_pages} "
        f"| {_number(one.friction.minutes_to_first_result)} | {cost} |"
    )


class Overall(Frozen):
    """The rates and the lines counted apart beside them pool the briefs that traced. A brief
    that did not trace is not a result, so its rates are pooled apart, in `untraced_*`."""

    model: str
    briefs: int
    finished: int
    session_failed: int
    not_run: int
    traced: int
    shown: Counted
    read: Counted
    strict_pass: Share
    coverage: Share
    untraced_strict_pass: Share
    untraced_coverage: Share
    agent_coverage: Share
    described_coverage: Share
    agent_measurements: int
    by: dict[By, Decided]
    uncovered: dict[str, int]
    median_confirmation_pages: float | None
    median_minutes_to_first_result: float | None
    refused_tool_calls: int
    cut_off: int
    cost_usd: float
    earlier_tries: int
    earlier_cost_usd: float
    asked_before_build: int = 0
    questions: int = 0
    searched_before_build: int = 0
    stated_unasked: Share = Share(numerator=0, denominator=0)
    older_traces: int = 0
    """Traced briefs whose result.json predates the `by` field, so they add nothing to `by`."""


class Summary(Frozen):
    overall: Overall
    briefs: tuple[BriefResult, ...]


def _pooled_by(traces: Sequence[Trace]) -> dict[By, Decided]:
    none = Decided(0, 0)
    return {
        by: Decided(
            sum(one.by.get(by, none).requirements for one in traces),
            sum(one.by.get(by, none).passes for one in traces),
        )
        for by in By
    }


def _pooled_uncovered(traces: Sequence[Trace]) -> dict[str, int]:
    families: Counter[str] = Counter()
    for one in traces:
        families.update(one.uncovered)
    return dict(families.most_common())


def summarize(
    results: Sequence[BriefResult],
    missing: Sequence[str],
    model: str,
    earlier: Sequence[BriefResult] = (),
) -> Summary:
    """`earlier` is the result of each try a brief was run again after. Only its cost counts."""
    finished = [one for one in results if one.status == "finished"]
    traces = [one.trace for one in finished if one.trace is not None]
    rated = [one for one in traces if one.traced]
    not_traced = [one for one in traces if not one.traced]
    minutes = [
        one.friction.minutes_to_first_result
        for one in finished
        if one.friction.minutes_to_first_result is not None
    ]
    pages = [float(one.friction.confirmation_pages) for one in finished]
    asked = [one.friction.asking for one in finished if one.friction.asking is not None]
    overall = Overall(
        model=model,
        briefs=len(results) + len(missing),
        finished=len(finished),
        session_failed=len(results) - len(finished),
        not_run=len(missing),
        traced=sum(one.traced for one in traces),
        shown=_pooled_counts([one.shown for one in traces]),
        read=_pooled_counts([one.read for one in traces]),
        strict_pass=pooled([one.strict_pass for one in rated]),
        coverage=pooled([one.coverage for one in rated]),
        untraced_strict_pass=pooled([one.strict_pass for one in not_traced]),
        untraced_coverage=pooled([one.coverage for one in not_traced]),
        agent_coverage=pooled([one.agent_coverage for one in rated]),
        described_coverage=pooled([one.described_coverage for one in rated]),
        agent_measurements=sum(len(one.agent_measurements) for one in traces),
        by=_pooled_by(rated),
        older_traces=sum(not one.by for one in rated),
        uncovered=_pooled_uncovered(rated),
        median_confirmation_pages=statistics.median(pages) if pages else None,
        median_minutes_to_first_result=statistics.median(minutes) if minutes else None,
        refused_tool_calls=sum(one.friction.refused_tool_calls for one in finished),
        cut_off=sum(len(one.cut_off) for one in traces),
        cost_usd=sum(one.cost_usd or 0.0 for one in (*results, *earlier)),
        earlier_tries=len(earlier),
        earlier_cost_usd=sum(one.cost_usd or 0.0 for one in earlier),
        asked_before_build=sum(one.asked_before_build for one in asked),
        questions=sum(one.questions for one in asked),
        searched_before_build=sum(one.searched_before_build for one in asked),
        stated_unasked=Share(
            numerator=sum(one.stated_unasked is True for one in asked),
            denominator=sum(one.stated_unasked is not None for one in asked),
        ),
    )
    return Summary(overall=overall, briefs=tuple(results))


def markdown(summary: Summary, missing: Sequence[str]) -> str:
    overall = summary.overall
    lines = [
        "# Brief-set run",
        "",
        f"model: {overall.model}",
        f"briefs: {overall.briefs}, finished: {overall.finished}, "
        f"session failed: {overall.session_failed}, not run: {overall.not_run}",
        f"traced: {overall.traced}/{overall.briefs}",
        f"cards the session was shown: {_cards(overall.shown)}",
        f"cards {READ_AFTER}: {_cards(overall.read)}",
        f"strict pass rate, over the {overall.traced} traced briefs: "
        f"{percent(overall.strict_pass)}",
        f"requirements covered by reviewed checks: {percent(overall.coverage)}",
        "requirements covered by agent-written checks the person approved: "
        f"{percent(overall.agent_coverage)}",
        "requirements decided on a load case the agent described, counted apart: "
        f"{percent(overall.described_coverage)}",
        *apart(overall.by, overall.uncovered),
        *_older(overall.older_traces),
        f"the {overall.finished - overall.traced} finished brief(s) that did not trace, counted "
        f"apart: strict pass {percent(overall.untraced_strict_pass)}, covered by reviewed checks "
        f"{percent(overall.untraced_coverage)}",
        f"agent measurements: {overall.agent_measurements}, not verified",
        f"confirmation pages per brief: median {_number(overall.median_confirmation_pages)}",
        f"minutes to first result: median {_number(overall.median_minutes_to_first_result)}",
        f"tool calls Claude Code refused as no such tool, model friction: "
        f"{overall.refused_tool_calls}",
        "check jobs with no stored result after the session (cut off, refused and not retried, "
        f"or timed out): {overall.cut_off}; their requirements count as by {By.WAITING}, and "
        "against both rates",
        f"asked before the first build: {overall.asked_before_build}/{overall.finished}, "
        f"{overall.questions} questions in all",
        f"searched before the first build: {overall.searched_before_build}/{overall.finished}",
        f"fully stated briefs that got no questions: {_fraction(overall.stated_unasked)}",
        f"cost: ${overall.cost_usd:.2f}, of which ${overall.earlier_cost_usd:.2f} on "
        f"{overall.earlier_tries} earlier tries",
        "",
        "| brief | domain | trace | strict pass | covered | pages | minutes | cost |",
        "|---|---|---|---|---|---|---|---|",
        *(_row(one) for one in summary.briefs),
        *(f"| {one} | - | not run | - | - | - | - | - |" for one in missing),
    ]
    for one in summary.briefs:
        if one.trace and one.trace.untraced:
            lines += ["", f"## Untraced in {one.id}", *(f"- {name}" for name in one.trace.untraced)]
        if one.trace and one.trace.cut_off:
            lines += ["", f"## Cut off in {one.id}", *(f"- {name}" for name in one.trace.cut_off)]
    return "\n".join(lines) + "\n"


def _older(count: int) -> list[str]:
    if not count:
        return []
    return [
        f"{count} traced brief(s) come from an older run that kept no `by` counts, so the "
        "requirements-by lines leave them out"
    ]


def _fraction(share: Share) -> str:
    return f"{share.numerator}/{share.denominator}" if share.denominator else "none marked"
