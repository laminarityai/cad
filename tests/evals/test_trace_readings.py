"""In build-first the agent scores before the person confirms, and Confirm judges the same stored
results. After the session the tracer reads each variant scored with a brief through the server's
own `scorecard` read, and the rates come from the reading of the last variant scored."""

import shutil
from pathlib import Path

from outcome import Share
from tracefacts import trace_session

from cad.briefs import store as briefs
from cad.checks.job_store import JOBS
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.scorecard.model import AwaitingConfirmation
from tests.support.cards import (
    BRIEF_TEXT,
    confirm_on_page,
    drafts,
    genuine_card,
    transcript_of,
    write_transcript,
)
from tests.support.readings import scored_variant

LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}, "under 150 g")
FRIENDLY = ({"kind": "unchecked", "statement": "looks friendly"}, "looks friendly")


def a_session(tmp_path: Path) -> tuple[Path, Path, Roots, str]:
    home = tmp_path / "home"
    variants = home / ".cad" / "variants"
    variants.mkdir(parents=True)
    roots = Roots(home / ".cad" / "briefs", home / ".cad" / "projects")
    brief_id = briefs.create_brief(roots, BRIEF_TEXT, new_project_id()).id
    return home, variants, roots, brief_id


def test_a_card_scored_before_confirm_is_judged_by_the_reading_after_the_session(
    tmp_path: Path,
) -> None:
    home, variants, roots, brief_id = a_session(tmp_path)
    vid = scored_variant(variants)
    shown = genuine_card(variant_id=vid, basis=AwaitingConfirmation(brief_id=brief_id))
    write_transcript(variants, shown)
    confirm_on_page(roots, brief_id, drafts(LIGHT, FRIENDLY))
    traced = trace_session(home, transcript_of(variants))
    assert traced.traced, traced.untraced
    assert (traced.cards, traced.judged, traced.awaiting) == (2, 1, 0)
    assert (traced.strict_pass, traced.coverage) == (
        Share(numerator=0, denominator=2),
        Share(numerator=1, denominator=2),
    )


def test_a_brief_the_person_never_confirmed_stays_awaiting(tmp_path: Path) -> None:
    home, variants, roots, brief_id = a_session(tmp_path)
    briefs.propose(roots, brief_id, drafts(LIGHT, FRIENDLY))
    vid = scored_variant(variants)
    write_transcript(
        variants, genuine_card(variant_id=vid, basis=AwaitingConfirmation(brief_id=brief_id))
    )
    traced = trace_session(home, transcript_of(variants))
    assert not traced.traced
    assert (traced.judged, traced.awaiting) == (0, 2)
    assert "2 card(s) still awaiting confirmation" in traced.untraced


def test_a_variant_judged_later_does_not_cover_another_variant(tmp_path: Path) -> None:
    home, variants, roots, brief_id = a_session(tmp_path)
    vid = scored_variant(variants)
    other = scored_variant(variants, "x = 2\n")
    basis = AwaitingConfirmation(brief_id=brief_id)
    confirm_on_page(roots, brief_id, drafts(LIGHT, FRIENDLY))
    shutil.rmtree(variants / other / JOBS)
    write_transcript(
        variants,
        genuine_card(variant_id=vid, basis=basis),
        genuine_card(variant_id=other, basis=basis),
    )
    traced = trace_session(home, transcript_of(variants))
    assert not traced.traced
    assert traced.awaiting == 1
    assert any(
        line.startswith(f"read after the session, {other}: Unreadable ") and "never" in line
        for line in traced.untraced
    ), traced.untraced
