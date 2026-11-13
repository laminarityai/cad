"""An honest retry after a refused background job. The sandbox refuses the stress job, the agent
scores the same variant again, and the second try stores a result. Once a job is stored the
server always shows it, so the refusal traces only when it comes before every card bound to that
record, and a later card shows the retry: the stored result, or the job still running."""

import json
import threading
from pathlib import Path

import pytest
from outcome import Trace
from tracefacts import trace_session

from cad.checks.jobs import JobResult, JobSpec
from cad.checks.result import Verdict
from cad.scorecard import score
from tests.support.background import (
    GONE,
    Card,
    Scoring,
    a_scoring,
    fea_of,
    ran,
    refused,
    sandbox,
)
from tests.support.cards import transcript_of, write_transcript

HOLDS = "unknown, but its signed job result holds pass"


def refused_then_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Scoring, Card, Card]:
    scoring = a_scoring(tmp_path, stated=True)
    sandbox(monkeypatch, refused)
    refusal = scoring.score()
    assert fea_of(refusal)["reason"] == GONE
    sandbox(monkeypatch, ran(Verdict.PASS))
    stored = scoring.score()
    assert fea_of(stored)["verdict"] == "pass"
    return scoring, refusal, stored


def shown(scoring: Scoring, *cards: Card) -> Trace:
    write_transcript(scoring.variants, *(json.dumps(card) for card in cards))
    return trace_session(scoring.home, transcript_of(scoring.variants))


def test_a_refusal_before_the_retry_that_stored_the_job_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scoring, refusal, stored = refused_then_stored(tmp_path, monkeypatch)
    traced = shown(scoring, refusal, stored)
    assert traced.traced, traced.untraced


def test_a_refusal_before_a_retry_still_running_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retry's card shows the job running, and the job is stored after it."""
    scoring = a_scoring(tmp_path, stated=True)
    sandbox(monkeypatch, refused)
    refusal = scoring.score()
    released = threading.Event()
    stores = ran(Verdict.PASS)

    def slow(job: JobSpec) -> JobResult:
        released.wait(30)
        return stores(job)

    sandbox(monkeypatch, slow)
    monkeypatch.setattr(score, "WAIT_SECONDS", 0.01)
    running = scoring.score()
    assert fea_of(running)["kind"] == "pending"
    released.set()
    monkeypatch.setattr(score, "WAIT_SECONDS", 30)
    assert fea_of(scoring.score())["verdict"] == "pass"
    traced = shown(scoring, refusal, running)
    assert traced.traced, traced.untraced


def test_a_refusal_after_a_card_bound_to_the_stored_job_is_untraced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scoring, refusal, stored = refused_then_stored(tmp_path, monkeypatch)
    traced = shown(scoring, stored, refusal, stored)
    assert not traced.traced
    assert [line for line in traced.untraced if line.endswith(HOLDS)], traced.untraced


def test_a_refusal_no_later_card_retries_is_untraced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scoring, refusal, _ = refused_then_stored(tmp_path, monkeypatch)
    traced = shown(scoring, refusal)
    assert not traced.traced
    assert [line for line in traced.untraced if line.endswith(HOLDS)], traced.untraced


def test_a_later_card_that_does_not_show_the_stored_job_retries_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scoring, refusal, stored = refused_then_stored(tmp_path, monkeypatch)
    fea_of(stored)["verdict"] = "fail"
    traced = shown(scoring, refusal, stored)
    assert not traced.traced
    assert [line for line in traced.untraced if line.endswith(HOLDS)], traced.untraced
