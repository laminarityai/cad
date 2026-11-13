"""A brief's trace counts the cards the session was shown apart from the server's readings after
it, so a new run's shown counts compare with a baseline taken before the tracer read anything.
Each untraced line names its origin, even for a shown card equal to its reading."""

from pathlib import Path

from outcome import BriefResult, Counted, Friction, Share, Trace
from readings import READ_AFTER
from summary import markdown, summarize
from tracefacts import failed_trace, trace_session

from cad.scorecard.model import AwaitingConfirmation
from tests.support.cards import (
    confirm_on_page,
    drafts,
    genuine_card,
    transcript_of,
    write_transcript,
)
from tests.support.readings import a_session, reading_of, scored_variant

LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}, "under 150 g")
FRIENDLY = ({"kind": "unchecked", "statement": "looks friendly"}, "looks friendly")


def test_the_trace_counts_the_cards_shown_apart_from_the_readings(tmp_path: Path) -> None:
    home, variants, roots, brief_id = a_session(tmp_path)
    vid = scored_variant(variants)
    basis = AwaitingConfirmation(brief_id=brief_id)
    write_transcript(variants, genuine_card(variant_id=vid, basis=basis))
    confirm_on_page(roots, brief_id, drafts(LIGHT, FRIENDLY))
    traced = trace_session(home, transcript_of(variants))
    assert traced.traced, traced.untraced
    assert (traced.shown.cards, traced.shown.judged) == (1, 0)
    assert (traced.read.cards, traced.read.judged) == (1, 1)
    assert traced.shown.numbers == traced.shown.resolved > 0
    assert traced.read.numbers == traced.read.resolved > 0


def test_a_shown_card_equal_to_its_reading_keeps_its_origin(tmp_path: Path) -> None:
    home, variants, _, brief_id = a_session(tmp_path)
    vid = scored_variant(variants, version="0" * 64)
    shown = reading_of(
        home, genuine_card(variant_id=vid, basis=AwaitingConfirmation(brief_id=brief_id))
    )
    write_transcript(variants, shown)
    traced = trace_session(home, transcript_of(variants))
    stale = [line for line in traced.untraced if ": Stale " in line]
    from_shown = [line for line in stale if line.startswith(f"{vid}: ")]
    from_read = [line for line in stale if line.startswith(f"{READ_AFTER}, {vid}: ")]
    assert from_shown and len(from_shown) == len(from_read) == len(stale) / 2, stale


def a_result(brief_id: str, trace: Trace) -> BriefResult:
    return BriefResult(
        id=brief_id,
        domain="tests",
        status="finished",
        model="m",
        cost_usd=0.5,
        turns=3,
        seconds=10,
        note=None,
        trace=trace,
        friction=Friction(confirmation_pages=1, ask_calls=1, minutes_to_first_result=0.5),
    )


def test_the_summary_reports_shown_and_read_apart_and_names_a_failed_trace() -> None:
    traced = Trace(
        traced=True,
        shown=Counted(cards=2, judged=1, numbers=40, resolved=40),
        read=Counted(cards=1, judged=1, numbers=25, resolved=25),
        awaiting=0,
        no_brief=0,
        untraced=(),
        agent_measurements=(),
        strict_pass=Share(numerator=1, denominator=2),
        coverage=Share(numerator=2, denominator=2),
    )
    results = [a_result("ok", traced), a_result("broken", failed_trace(RuntimeError("boom")))]
    summary = summarize(results, [], "m")
    assert summary.overall.shown == Counted(cards=2, judged=1, numbers=40, resolved=40)
    assert summary.overall.read == Counted(cards=1, judged=1, numbers=25, resolved=25)
    text = markdown(summary, [])
    assert "cards the session was shown: 2, 1 judged, 40/40 numbers resolved" in text
    assert f"cards {READ_AFTER}: 1, 1 judged, 25/25 numbers resolved" in text
    [broken] = [line for line in text.splitlines() if line.startswith("| broken |")]
    assert broken.count("trace failed") == 2 and "no requirements" not in broken, broken
