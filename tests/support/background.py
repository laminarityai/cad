"""Sessions whose cards come from the server's own `score_variant`, with only the sandbox run
stood in, so a background job can be refused, killed or stored as a test needs."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cad.accounts.principal import AccountId
from cad.briefs import assumptions
from cad.briefs.assumptions import Assumption
from cad.checks import lanes
from cad.checks.container.check import Quick
from cad.checks.jobs import JobResult, JobSpec
from cad.checks.report import QUICK, SPECS, unknown_for_all
from cad.checks.result import StepMissing, StepStored, Verdict, Where
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.operations.model import Tenant
from cad.operations.scorecards import ScoreVariantInput, score_variant
from cad.operations.tenants import open_tenant
from cad.records.roots import Roots
from cad.sandbox.outcome import SandboxUnavailable
from tests.support.cards import KEY, STEP_SHA, TARGET, confirm_on_page, drafts, genuine_result
from tests.support.load_cases import hole_hook
from tests.support.readings import a_session, built

FEA = next(spec for spec in SPECS if spec.id == "fea")
IMAGE = "sha256:" + "i" * 64
GONE = "the sandbox went away"
KILLED = "the check container ran past 600 s and was killed before it sent a report"
LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}, "under 150 g")
STRONG = ({"kind": "min_safety_factor", "load": hole_hook(), "factor": 2}, "looks friendly")

type Background = Callable[[JobSpec], JobResult]
type Card = dict[str, Any]


def refused(job: JobSpec) -> JobResult:
    del job
    raise SandboxUnavailable(GONE)


def ran(verdict: Verdict, timed_out: bool = False, where: Where | None = None) -> Background:
    def run(job: JobSpec) -> JobResult:
        result = genuine_result(FEA).model_copy(
            update={"instance": job.instance, "verdict": verdict, "where": where}
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


@dataclass(frozen=True, slots=True)
class Scoring:
    """One built variant under a brief whose load the person stated or the agent assumed."""

    home: Path
    roots: Roots
    brief_id: str
    tenant: Tenant
    variant_id: str

    @property
    def variants(self) -> Path:
        return self.home / ".cad" / "variants"

    def score(self) -> Card:
        arguments = ScoreVariantInput(
            variant_id=self.variant_id, material_key=KEY, brief_id=self.brief_id
        )
        return json.loads(score_variant(self.tenant, arguments).model_dump_json(by_alias=True))


def a_scoring(tmp_path: Path, stated: bool) -> Scoring:
    """A stated load is confirmed before the first score. An assumed one is confirmed by
    `confirm_assumed` after the session."""
    home, variants, roots, brief_id = a_session(tmp_path)
    tenant = open_tenant(
        AccountId("local"), roots, variants, home / ".cad" / "geometry", None, Door(), ingest
    )
    if stated:
        confirm_on_page(roots, brief_id, drafts(LIGHT, STRONG))
    else:
        target = TARGET.validate_python(STRONG[0])
        assumptions.assume(roots, brief_id, [Assumption(target=target, why="49 N assumed")], ())
    return Scoring(home, roots, brief_id, tenant, built(variants).id)


def confirm_assumed(scoring: Scoring) -> None:
    confirm_on_page(scoring.roots, scoring.brief_id, drafts(LIGHT))


def fea_of(card: Card) -> dict[str, Any]:
    (fea,) = (one for one in card["results"] if one["check_id"] == "fea")
    return fea
