"""The tracer reads a card as the server reports it: a result under a load nobody confirmed is a
measure_only result, and a card from the scorecard tool carries an etag."""

from pathlib import Path

import pytest
from chain import CheckStep, Resolved
from trace_store import SPEC_BY_ID, main

from cad.briefs import store as briefs
from cad.projects.model import new_project_id
from cad.scorecard import material, unjudged
from cad.scorecard.material import ReportedScorecard
from cad.scorecard.model import AwaitingConfirmation
from tests.support.cards import (
    BRIEF_TEXT,
    genuine_card,
    genuine_result,
    lines,
    roots_beside,
    trace,
    transcript_of,
    write_transcript,
)

LOAD = "9ae13218"


def reported_with_a_measure_only(store: Path) -> ReportedScorecard:
    roots = roots_beside(store)
    brief_id = briefs.create_brief(roots, BRIEF_TEXT, new_project_id()).id
    fea = genuine_result(SPEC_BY_ID["fea"]).model_copy(update={"instance": LOAD})
    card = genuine_card(basis=AwaitingConfirmation(brief_id=brief_id))
    results = unjudged.without_verdicts((*card.results, fea), frozenset({("fea", LOAD)}))
    return material.reported(card, None).model_copy(update={"results": results})


def test_a_measure_only_result_traces_each_measure_to_its_check(store: Path) -> None:
    card = reported_with_a_measure_only(store)
    assert isinstance(card.results[-1], unjudged.MeasureOnly)
    traced = trace(card, store)
    fea = [one for one in traced.numbers if one.label.startswith("fea.")]
    assert len(fea) == len(SPEC_BY_ID["fea"].measures)
    assert all(
        isinstance(one.outcome, Resolved)
        and one.outcome.steps[0] == CheckStep("fea", SPEC_BY_ID["fea"].version)
        for one in fea
    )
    assert traced.failures == ()


def test_a_card_from_the_scorecard_tool_is_read(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = material.snapshot(reported_with_a_measure_only(store))
    write_transcript(store, snapshot.model_dump_json())
    roots = roots_beside(store)
    code = main(
        [
            str(transcript_of(store)),
            "--root",
            str(store),
            "--briefs-root",
            str(roots.briefs),
            "--projects-root",
            str(roots.projects),
        ]
    )
    out = lines(capsys)
    assert "cards unreadable: 0" in out
    assert code == 0, out
