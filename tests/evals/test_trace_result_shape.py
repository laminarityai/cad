"""A shown result must carry the verdict and the measures its signed job result holds. A card that
changes a verdict and drops every measure, so no number is left to bind, or that drops one measure
and keeps the verdict, is untraced."""

from pathlib import Path

from tracefacts import trace_session

from cad.checks.result import Verdict
from cad.scorecard.model import AwaitingConfirmation, Scorecard
from tests.support.cards import (
    confirm_on_page,
    drafts,
    genuine_card,
    result_of,
    transcript_of,
    with_result,
    write_transcript,
)
from tests.support.readings import a_session, scored_variant

LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}, "under 150 g")
FRIENDLY = ({"kind": "unchecked", "statement": "looks friendly"}, "looks friendly")


def untraced_after(tmp_path: Path, check_id: str, **change: object) -> tuple[str, ...]:
    """Score a variant, show the session a card with `change` made to its `check_id` result,
    confirm, and trace."""
    home, variants, roots, brief_id = a_session(tmp_path)
    vid = scored_variant(variants)
    card: Scorecard = genuine_card(variant_id=vid, basis=AwaitingConfirmation(brief_id=brief_id))
    write_transcript(variants, with_result(card, check_id, **change))
    confirm_on_page(roots, brief_id, drafts(LIGHT, FRIENDLY))
    traced = trace_session(home, transcript_of(variants))
    assert traced.traced == (not traced.untraced)
    return traced.untraced


def test_a_verdict_changed_on_a_result_with_no_measures_is_untraced(tmp_path: Path) -> None:
    untraced = untraced_after(tmp_path, "min_wall", verdict=Verdict.FAIL, measured=())
    assert any("min_wall" in line for line in untraced), untraced


def test_a_result_that_drops_a_measure_is_untraced(tmp_path: Path) -> None:
    held = result_of(genuine_card(), "extents")
    assert len(held.measured) > 1
    untraced = untraced_after(tmp_path, "extents", measured=held.measured[:1])
    assert any("extents" in line for line in untraced), untraced
