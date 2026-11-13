import statistics
from collections import Counter
from collections.abc import Sequence

from outcome import BriefResult, Frozen, Share, Trace
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
    strict = percent(trace.strict_pass) if trace else "-"
    coverage = percent(trace.coverage) if trace else "-"
    cost = "-" if one.cost_usd is None else f"${one.cost_usd:.2f}"
    return (
        f"| {one.id} | {one.domain} | {verdict} | {strict} | {coverage} "
        f"| {one.friction.confirmation_pages} "
        f"| {_number(one.friction.minutes_to_first_result)} | {cost} |"
    )


class Overall(Frozen):
    model: str
    briefs: int
    finished: int
    session_failed: int
    not_run: int
    traced: int
    strict_pass: Share
    coverage: Share
    agent_coverage: Share
    described_coverage: Share
    agent_measurements: int
    by: dict[By, Decided]
    uncovered: dict[str, int]
    median_confirmation_pages: float | None
    median_minutes_to_first_result: float | None
    cost_usd: float


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


def summarize(results: Sequence[BriefResult], missing: Sequence[str], model: str) -> Summary:
    finished = [one for one in results if one.status == "finished"]
    traces = [one.trace for one in finished if one.trace is not None]
    minutes = [
        one.friction.minutes_to_first_result
        for one in finished
        if one.friction.minutes_to_first_result is not None
    ]
    pages = [float(one.friction.confirmation_pages) for one in finished]
    overall = Overall(
        model=model,
        briefs=len(results) + len(missing),
        finished=len(finished),
        session_failed=len(results) - len(finished),
        not_run=len(missing),
        traced=sum(one.traced for one in traces),
        strict_pass=pooled([one.strict_pass for one in traces]),
        coverage=pooled([one.coverage for one in traces]),
        agent_coverage=pooled([one.agent_coverage for one in traces]),
        described_coverage=pooled([one.described_coverage for one in traces]),
        agent_measurements=sum(len(one.agent_measurements) for one in traces),
        by=_pooled_by(traces),
        uncovered=_pooled_uncovered(traces),
        median_confirmation_pages=statistics.median(pages) if pages else None,
        median_minutes_to_first_result=statistics.median(minutes) if minutes else None,
        cost_usd=sum(one.cost_usd or 0.0 for one in results),
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
        f"strict pass rate: {percent(overall.strict_pass)}",
        f"requirements covered by reviewed checks: {percent(overall.coverage)}",
        "requirements covered by agent-written checks the person approved: "
        f"{percent(overall.agent_coverage)}",
        "requirements decided on a load case the agent described, counted apart: "
        f"{percent(overall.described_coverage)}",
        *apart(overall.by, overall.uncovered),
        f"agent measurements: {overall.agent_measurements}, not verified",
        f"confirmation pages per brief: median {_number(overall.median_confirmation_pages)}",
        f"minutes to first result: median {_number(overall.median_minutes_to_first_result)}",
        f"cost: ${overall.cost_usd:.2f}",
        "",
        "| brief | domain | trace | strict pass | covered | pages | minutes | cost |",
        "|---|---|---|---|---|---|---|---|",
        *(_row(one) for one in summary.briefs),
        *(f"| {one} | - | not run | - | - | - | - | - |" for one in missing),
    ]
    for one in summary.briefs:
        if one.trace and one.trace.untraced:
            lines += ["", f"## Untraced in {one.id}", *(f"- {name}" for name in one.trace.untraced)]
    return "\n".join(lines) + "\n"
