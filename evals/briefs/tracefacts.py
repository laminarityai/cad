from pathlib import Path

from outcome import Share, Trace
from provenance import NotVerified, Stale, Unresolved
from trace_store import TracedCard, TracedStore, exit_code, tally, trace_root
from tracking import NoRequirements, track
from tracking import Share as TrackedShare

from cad.records.roots import Roots

NO_CARD = "no scorecard was stored"


def _share(found: TrackedShare) -> Share:
    if isinstance(found, NoRequirements):
        return Share(numerator=0, denominator=0)
    return Share(numerator=found.numerator, denominator=found.denominator)


def _latest_stored_card(found: TracedStore) -> TracedCard:
    return max(found.cards, key=lambda one: one.path.stat().st_mtime)


def trace_session(home: Path) -> Trace:
    stores = home / ".cad"
    found: TracedStore = trace_root(
        stores / "variants", Roots(briefs=stores / "briefs", projects=stores / "projects")
    )
    counts = tally(found.traces)
    untraced: list[str] = []
    measured: list[str] = []
    for card in found.traces:
        untraced += [
            f"{card.variant_id}: {type(one).__name__} {one.reason}" for one in card.failures
        ]
        for number in card.numbers:
            outcome = number.outcome
            head = f"{card.variant_id}: {number.label} = {number.value}"
            if isinstance(outcome, Stale | Unresolved):
                untraced.append(f"{head}: {type(outcome).__name__} {outcome.reason}")
            elif isinstance(outcome, NotVerified):
                measured.append(f"{head}: {outcome.reason}")
    if counts.awaiting:
        untraced.append(f"{counts.awaiting} card(s) still awaiting confirmation")
    if counts.no_brief:
        untraced.append(f"{counts.no_brief} card(s) scored with no brief")
    if not counts.cards:
        untraced.append(NO_CARD)
    tracking = track(_latest_stored_card(found).outcomes if found.cards else ())
    return Trace(
        traced=exit_code(counts, require_judged=True) == 0,
        cards=counts.cards,
        judged=counts.judged,
        awaiting=counts.awaiting,
        no_brief=counts.no_brief,
        numbers=counts.numbers,
        resolved=counts.resolved,
        untraced=tuple(untraced),
        agent_measurements=tuple(measured),
        strict_pass=_share(tracking.strict_pass_rate),
        coverage=_share(tracking.reviewed_coverage),
    )
