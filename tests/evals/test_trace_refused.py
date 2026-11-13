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

from cad.accounts.principal import AccountId
from cad.briefs import assumptions
from cad.briefs.assumptions import Assumption
from cad.checks import lanes
from cad.checks.container.check import Quick
from cad.checks.jobs import JobResult, JobSpec
from cad.checks.report import QUICK, SPECS, unknown_for_all
from cad.checks.result import StepMissing, StepStored, Verdict
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.operations.scorecards import ScoreVariantInput, score_variant
from cad.operations.tenants import open_tenant
from cad.sandbox.outcome import SandboxUnavailable
from tests.support.cards import (
    KEY,
    STEP_SHA,
    TARGET,
    confirm_on_page,
    drafts,
    genuine_result,
    transcript_of,
    write_transcript,
)
from tests.support.load_cases import hole_hook
from tests.support.readings import a_session, built

FEA = next(spec for spec in SPECS if spec.id == "fea")
IMAGE = "sha256:" + "i" * 64
GONE = "the sandbox went away"
KILLED = "the check container ran past 600 s and was killed before it sent a report"
LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}, "under 150 g")
STRONG = ({"kind": "min_safety_factor", "load": hole_hook(), "factor": 2}, "looks friendly")

type Background = Callable[[JobSpec], JobResult]


def refused(job: JobSpec) -> JobResult:
    del job
    raise SandboxUnavailable(GONE)


def ran(verdict: Verdict, timed_out: bool = False) -> Background:
    def run(job: JobSpec) -> JobResult:
        result = genuine_result(FEA).model_copy(
            update={"instance": job.instance, "verdict": verdict}
        )
        return JobResult(
            check_image_digest=IMAGE,
            step=StepMissing(reason="no STEP"),
            results=(result,),
            timed_out=timed_out,
        )

    return run


def killed(job: JobSpec) -> JobResult:
    (result,) = unknown_for_all(KILLED, (FEA,))
    return JobResult(
        check_image_digest=IMAGE,
        step=StepMissing(reason=KILLED),
        results=(result.model_copy(update={"instance": job.instance}),),
        timed_out=True,
    )


def sandbox(monkeypatch: pytest.MonkeyPatch, background: Background) -> None:
    def run(job: JobSpec) -> JobResult:
        if isinstance(job.budget, Quick):
            return JobResult(
                check_image_digest=IMAGE,
                step=StepStored(sha256=STEP_SHA),
                results=tuple(genuine_result(spec) for spec in QUICK),
            )
        return background(job)

    monkeypatch.setattr(lanes.LANES, "_run", run)


def session(
    tmp_path: Path, stated: bool, change: Callable[[dict[str, Any]], None] | None = None
) -> tuple[Trace, dict[str, Any]]:
    """Score one variant through `score_variant` under a load the person stated and confirmed
    first, or one the agent assumed, show the session the card with `change` made to its fea
    result, confirm, and trace. Returns the trace and the fea result as the server showed it."""
    home, variants, roots, brief_id = a_session(tmp_path)
    tenant = open_tenant(
        AccountId("local"), roots, variants, home / ".cad" / "geometry", None, Door(), ingest
    )
    rows = drafts(LIGHT, STRONG) if stated else drafts(LIGHT)
    if stated:
        confirm_on_page(roots, brief_id, rows)
    else:
        target = TARGET.validate_python(STRONG[0])
        assumptions.assume(roots, brief_id, [Assumption(target=target, why="49 N assumed")], ())
    held = built(variants)
    arguments = ScoreVariantInput(variant_id=held.id, material_key=KEY, brief_id=brief_id)
    card = json.loads(score_variant(tenant, arguments).model_dump_json(by_alias=True))
    (fea,) = (one for one in card["results"] if one["check_id"] == "fea")
    shown = dict(fea)
    if change is not None:
        change(fea)
    write_transcript(variants, json.dumps(card))
    if not stated:
        confirm_on_page(roots, brief_id, rows)
    return trace_session(home, transcript_of(variants)), shown


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
