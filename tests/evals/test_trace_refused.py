"""The server shows a result for a background job it refused, or one that ran past its time
limit, and stores neither. Such a result traces only when it is exactly what the server shows for
a refused job of its check and instance, and only when no signed record holds that job. The cards
come from the server's own `score_variant`, with only the sandbox run stood in."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from outcome import Trace
from tracefacts import trace_session

from cad.checks.report import unknown_for_all
from cad.checks.result import Verdict
from cad.scorecard.unjudged import MeasureOnly
from tests.support.background import (
    FEA,
    GONE,
    KILLED,
    Background,
    a_scoring,
    confirm_assumed,
    fea_of,
    killed,
    ran,
    refused,
    sandbox,
)
from tests.support.cards import genuine_result, transcript_of, write_transcript


def session(
    tmp_path: Path, stated: bool, change: Callable[[dict[str, Any]], None] | None = None
) -> tuple[Trace, dict[str, Any]]:
    """Score one variant through `score_variant` under a load the person stated and confirmed
    first, or one the agent assumed, show the session the card with `change` made to its fea
    result, confirm, and trace. Returns the trace and the fea result as the server showed it."""
    scoring = a_scoring(tmp_path, stated)
    card = scoring.score()
    fea = fea_of(card)
    shown = dict(fea)
    if change is not None:
        change(fea)
    write_transcript(scoring.variants, json.dumps(card))
    if not stated:
        confirm_assumed(scoring)
    return trace_session(scoring.home, transcript_of(scoring.variants)), shown


@pytest.mark.parametrize("background", [refused, killed], ids=["refused", "killed"])
@pytest.mark.parametrize("stated", [True, False], ids=["stated", "assumed"])
def test_a_card_whose_background_job_the_server_did_not_store_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, background: Background, stated: bool
) -> None:
    sandbox(monkeypatch, background)
    traced, shown = session(tmp_path, stated)
    assert shown["reason"] in (GONE, KILLED)
    assert shown.get("verdict", "unknown") == "unknown"
    assert shown["measured"] == []
    assert traced.traced, traced.untraced


@pytest.mark.parametrize("verdict", [Verdict.PASS, Verdict.FAIL])
def test_a_refusal_shown_in_place_of_a_signed_result_is_untraced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: Verdict
) -> None:
    sandbox(monkeypatch, ran(verdict))

    def forge(fea: dict[str, Any]) -> None:
        (result,) = unknown_for_all(GONE, (FEA,))
        refusal = result.model_copy(update={"instance": fea["instance"]})
        fea.clear()
        fea.update(refusal.model_dump(mode="json"))

    traced, shown = session(tmp_path, stated=True, change=forge)
    assert shown["verdict"] == verdict
    assert not traced.traced
    assert any(
        line.endswith(f"unknown, but its signed job result holds {verdict}")
        for line in traced.untraced
    ), traced.untraced


def with_measure(fea: dict[str, Any]) -> None:
    fea["measured"] = [genuine_result(FEA).measured[0].model_dump(mode="json")]


def passing(fea: dict[str, Any]) -> None:
    fea["verdict"] = "pass"


def with_faces(fea: dict[str, Any]) -> None:
    fea["where"] = {"support": [3], "load": [7]}


def elsewhere(fea: dict[str, Any]) -> None:
    fea["instance"] = "0" * 8


@pytest.mark.parametrize("change", [with_measure, passing, with_faces, elsewhere])
def test_a_refusal_carrying_what_no_refusal_shows_is_untraced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: Callable[[dict[str, Any]], None]
) -> None:
    sandbox(monkeypatch, refused)
    traced, _ = session(tmp_path, stated=True, change=change)
    assert not traced.traced
    assert any("Unsigned no signed job result holds fea for" in line for line in traced.untraced)


def test_a_timed_out_result_with_its_measures_is_untraced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job that ran past its time limit after its report line was whole shows that report,
    measures and verdict included, and the server stores none of it."""
    sandbox(monkeypatch, ran(Verdict.PASS, timed_out=True))
    traced, shown = session(tmp_path, stated=True)
    assert shown["verdict"] == "pass"
    assert shown["measured"]
    assert not traced.traced
    assert any("Unsigned no signed job result holds fea for" in line for line in traced.untraced)


def test_a_refusal_on_a_confirmed_load_shown_measure_only_is_untraced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server shows a result on a confirmed load with its verdict, so a card that drops it
    fails as misjudged instead of stopping the tracer."""
    sandbox(monkeypatch, refused)

    def measure_only(fea: dict[str, Any]) -> None:
        del fea["verdict"]
        fea.update(kind="measure_only", label=MeasureOnly.model_fields["label"].default)

    traced, _ = session(tmp_path, stated=True, change=measure_only)
    assert not traced.traced
    assert not traced.failed
    assert any(
        "Misjudged requirement" in line and "shows its fea result with no verdict" in line
        for line in traced.untraced
    ), traced.untraced
