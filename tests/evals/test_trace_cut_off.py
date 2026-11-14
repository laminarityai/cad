"""A stress job still running when the session ends never reports, since the server ends its checks
when it stops. The trace names it as cut off and counts its requirement against both rates."""

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from tracefacts import trace_session
from tracking import By

from cad.checks.jobs import JobResult, JobSpec
from cad.checks.result import Verdict
from cad.scorecard import score
from tests.support.background import a_scoring, fea_of, ran, sandbox
from tests.support.cards import transcript_of, write_transcript


@pytest.fixture
def held() -> Iterator[threading.Event]:
    released = threading.Event()
    yield released
    released.set()


def test_a_job_the_sessions_end_cut_off_is_named_and_counts_against_the_rates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, held: threading.Event
) -> None:
    stores = ran(Verdict.PASS)

    def never_reports(job: JobSpec) -> JobResult:
        held.wait(30)
        return stores(job)

    sandbox(monkeypatch, never_reports)
    monkeypatch.setattr(score, "WAIT_SECONDS", 0.01)
    scoring = a_scoring(tmp_path, stated=True)
    card = scoring.score()
    fea = fea_of(card)
    assert fea["kind"] == "pending"
    write_transcript(scoring.variants, json.dumps(card))
    traced = trace_session(scoring.home, transcript_of(scoring.variants))
    assert traced.traced, traced.untraced
    assert traced.cut_off == (f"{scoring.variant_id}: fea for {fea['instance']}",)
    assert traced.by[By.WAITING].requirements == 1
    assert traced.coverage.numerator < traced.coverage.denominator
