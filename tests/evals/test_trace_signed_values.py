"""Each result on a card the session was shown must equal the server's reading of the same
variant, material and brief, which rests on the stored, signed job result. A card whose value or
verdict was changed, or that carries another variant's results, is untraced, and the reason names
both values."""

from pathlib import Path

from tracefacts import trace_session

from cad.checks.result import Measure, Verdict
from cad.scorecard.model import AwaitingConfirmation
from cad.tables.materials import UNITS
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


def untraced_after(tmp_path: Path, change: str) -> tuple[str, tuple[str, ...]]:
    """Score a variant, show the session a card with `change` made to its mass result, confirm,
    and trace."""
    home, variants, roots, brief_id = a_session(tmp_path)
    vid = scored_variant(variants)
    card = genuine_card(variant_id=vid, basis=AwaitingConfirmation(brief_id=brief_id))
    stored = result_of(card, "mass")
    if change == "value":
        measured = tuple(
            Measure(name="mass", value=UNITS.Quantity(2.0, "kg")) if one.name == "mass" else one
            for one in stored.measured
        )
        card = with_result(card, "mass", measured=measured)
    else:
        card = with_result(card, "mass", verdict=Verdict.FAIL)
    write_transcript(variants, card)
    confirm_on_page(roots, brief_id, drafts(LIGHT, FRIENDLY))
    traced = trace_session(home, transcript_of(variants))
    assert not traced.traced
    assert traced.read.numbers == traced.read.resolved, traced.untraced
    return vid, traced.untraced


def test_a_shown_value_the_reading_does_not_hold_is_untraced(tmp_path: Path) -> None:
    vid, untraced = untraced_after(tmp_path, "value")
    assert untraced == (
        f"{vid}: mass.mass = 2 kilogram: Unresolved mass is 2 kg on the card, but the server's "
        "reading holds 1 kg",
    )


def test_a_shown_verdict_the_reading_does_not_hold_leaves_the_result_untraced(
    tmp_path: Path,
) -> None:
    vid, untraced = untraced_after(tmp_path, "verdict")
    assert len(untraced) == 4, untraced
    assert all(
        line.startswith(f"{vid}: mass.")
        and line.endswith(
            "Unresolved the card shows mass fail, but the server's reading holds pass"
        )
        for line in untraced
    ), untraced
