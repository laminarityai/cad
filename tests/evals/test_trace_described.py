"""Harness case 6, the tracer: a verdict on a described load case counts on a line of its own, in
neither headline number, and a card whose label does not match its confirmed load case fails."""

from pathlib import Path
from typing import Any

import pytest
from trace_store import SPEC_BY_ID, main
from tracking import By, Ratio, describe_apart, outcomes_of, track

from cad.briefs import store as briefs
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.scorecard import requirements
from cad.scorecard.model import AgainstBrief, Basis, Checked, Scorecard
from cad.scorecard.requirements import against
from tests.support.cards import (
    BRIEF_TEXT,
    confirm_on_page,
    drafts,
    genuine_card,
    genuine_result,
    lines,
    roots_beside,
    transcript_of,
    write_transcript,
)
from tests.support.load_cases import hole_hook, shelf

QUOTE = "A plate under 150 g"


def card_for(roots: Roots, load: dict[str, Any]) -> Scorecard:
    brief_id = briefs.create_brief(roots, BRIEF_TEXT, new_project_id()).id
    target = {"kind": "min_safety_factor", "load": load, "factor": 1}
    confirmed = confirm_on_page(roots, brief_id, drafts((target, QUOTE)))
    [one] = confirmed.requirements
    solved = genuine_result(SPEC_BY_ID["fea"]).model_copy(
        update={"instance": requirements.instance(one.target)}
    )
    card = genuine_card()
    card = card.model_copy(update={"results": (*card.results, solved)})
    basis: Basis = against(confirmed)(card.finished)
    return card.model_copy(update={"basis": basis})


def relabelled(card: Scorecard, label: str | None) -> Scorecard:
    basis = card.basis
    assert isinstance(basis, AgainstBrief)
    [row] = basis.requirements
    assert isinstance(row, Checked)
    held = basis.model_copy(update={"requirements": (row.model_copy(update={"load_case": label}),)})
    return card.model_copy(update={"basis": held})


def arguments(store: Path) -> list[str]:
    roots = roots_beside(store)
    return [
        str(transcript_of(store)),
        "--root",
        str(store),
        "--briefs-root",
        str(roots.briefs),
        "--projects-root",
        str(roots.projects),
    ]


def test_a_described_verdict_counts_apart_and_in_neither_headline(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    card = card_for(roots_beside(store), shelf())
    write_transcript(store, card)
    assert main([*arguments(store), "--require-judged"]) == 0
    out = lines(capsys)
    assert "misjudged: 0" in out
    assert "requirements decided on a load case the agent described, counted apart: 1/1" in out
    assert "strict pass rate: 0/1 (0%)" in out
    assert "requirements covered by reviewed checks: 0/1 (0%)" in out
    assert f"requirements by {By.DESCRIBED}: 1," in out


def test_a_reviewed_verdict_is_not_counted_as_described(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_transcript(store, card_for(roots_beside(store), hole_hook()))
    assert main([*arguments(store), "--require-judged"]) == 0
    out = lines(capsys)
    assert "counted apart: 0/1" in out
    assert "requirements covered by reviewed checks: 1/1 (100%)" in out


def test_a_described_card_with_no_label_is_misjudged(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_transcript(store, relabelled(card_for(roots_beside(store), shelf()), None))
    assert main(arguments(store)) == 1
    out = lines(capsys)
    assert "MISJUDGED" in out
    assert "carries no label, and its confirmed load case needs the described label" in out


def test_a_reviewed_card_with_the_label_is_misjudged(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_transcript(store, relabelled(card_for(roots_beside(store), hole_hook()), "described"))
    assert main(arguments(store)) == 1
    out = lines(capsys)
    assert "MISJUDGED" in out
    assert "carries the described label, and its confirmed load case needs none" in out


def test_the_summary_line_of_each_count_names_who_decided(store: Path) -> None:
    tracking = track(outcomes_of(card_for(roots_beside(store), shelf())))
    assert tracking.described_coverage == Ratio(1, 1)
    assert any(str(By.DESCRIBED) in line for line in describe_apart(tracking))
