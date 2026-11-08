from collections.abc import Callable
from pathlib import Path

import pytest

from cad.checks import job_store, jobs
from cad.checks.container.check import Quick
from cad.checks.container.wire import LoadCaseWire
from cad.checks.jobs import JobResult, Plan, Refused
from cad.checks.lanes import Done, Pending, Settled
from cad.checks.report import QUICK, SPECS, build_request, unknown_for_all
from cad.checks.result import CheckResult, ReadCited, ReadMissing, StepMissing, Verdict
from cad.sandbox import container
from cad.sandbox.container import Job, Ran
from cad.scorecard import score
from cad.scorecard.model import Basis, NoBrief, PendingCheck, Scorecard
from cad.tables.materials import load_materials
from cad.variants.entry import Entry, VariantId

POISSON_UNKNOWN = "the materials table has no poisson_ratio for prusament-pla: it says unknown"

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
PLATE_SHELL = PLATE + "from build123d import Shell\nresult = Shell(result.faces()[:-1])\n"
FEA = SPECS[4]
CASE: LoadCaseWire = {
    "support": {"kind": "flat_end"},
    "load": {"kind": "far_end", "force_n": 10.0, "direction": {"kind": "any"}},
}

type Build = Callable[[str], str]


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    real_run = container.run
    kinds: list[str] = []

    def run(job: Job) -> Ran:
        kinds.append(job.kind)
        return real_run(job)

    monkeypatch.setattr(container, "run", run)
    return kinds


def test_a_second_score_starts_no_container_and_gives_the_same_card_bytes(
    built: Build, store: Path, started: list[str]
) -> None:
    variant_id = built(PLATE + "# scored twice\n")
    started.clear()
    first = score.score_variant(variant_id, "prusament-pla", store)
    assert started == ["check"]
    second = score.score_variant(variant_id, "prusament-pla", store)
    assert started == ["check"]
    assert second.model_dump_json() == first.model_dump_json()


def test_another_material_runs_the_checks_again(
    built: Build, store: Path, started: list[str]
) -> None:
    variant_id = built(PLATE + "# two materials\n")
    started.clear()
    pla = score.score_variant(variant_id, "prusament-pla", store)
    petg = score.score_variant(variant_id, "prusament-petg", store)
    assert started == ["check", "check"]
    assert pla.finished[2].number("mass", "g") != petg.finished[2].number("mass", "g")


def test_a_tampered_job_result_is_run_again_and_never_trusted(
    built: Build, store: Path, started: list[str]
) -> None:
    variant_id = built(PLATE_SHELL)
    honest = score.score_variant(variant_id, "prusament-pla", store)
    assert honest.finished[0].verdict == Verdict.FAIL
    (path,) = (store / variant_id / job_store.JOBS).glob("*.signed")
    path.write_bytes(path.read_bytes().replace(b'"fail"', b'"pass"'))
    started.clear()
    again = score.score_variant(variant_id, "prusament-pla", store)
    assert started == ["check"]
    assert again == honest


def background_plan(root: Path) -> Plan:
    held = Entry(VariantId("0123456789abcdef"), root, b"brep", "b" * 64)
    table = load_materials()
    return jobs.plan(root, held, build_request("prusament-pla", table), table, {"c1": CASE})


def quick_result() -> JobResult:
    return JobResult(
        check_image_digest="sha256:" + "i" * 64,
        step=StepMissing(reason="offline"),
        results=unknown_for_all("offline"),
    )


def assembled(root: Path, outcome: Done | Pending | Refused) -> tuple[Scorecard, list[str]]:
    seen: list[str] = []

    def assess(results: score.Results) -> Basis:
        seen.extend(one.check_id for one in results if isinstance(one, CheckResult))
        return NoBrief()

    plan = background_plan(root)
    request = plan.quick.request
    return score.scorecard_of(plan, request, Settled(quick_result(), (outcome,)), assess), seen


def test_a_pending_background_check_holds_its_place_and_no_verdict(tmp_path: Path) -> None:
    card, assessed = assembled(tmp_path, Pending())
    assert [one.check_id for one in card.results] == [spec.id for spec in SPECS]
    assert card.results[4] == PendingCheck(
        check_id="fea",
        formula=FEA.formula,
        sources=FEA.sources,
        version=FEA.version,
        instance="c1",
        reads=(
            ReadCited(field="elastic_modulus"),
            ReadMissing(field="poisson_ratio", reason=POISSON_UNKNOWN),
            ReadCited(field="yield_strength"),
        ),
    )
    assert card.pending == ("fea",)
    assert assessed == ["closed_solid", "interference", "mass", "extents"]
    assert Scorecard.model_validate_json(card.model_dump_json()) == card


def test_a_refused_background_check_is_unknown_with_the_reason(tmp_path: Path) -> None:
    card, _ = assembled(tmp_path, Refused("the account has no analysis time left"))
    assert card.pending == ()
    assert card.finished[4].verdict == Verdict.UNKNOWN
    assert card.finished[4].reason == "the account has no analysis time left"
    assert card.finished[4].instance == "c1"


def test_a_card_must_list_exactly_its_pending_checks(tmp_path: Path) -> None:
    card, _ = assembled(tmp_path, Pending())
    with pytest.raises(ValueError, match="pending must list"):
        Scorecard.model_validate({**card.model_dump(), "pending": []})


def test_with_no_demand_one_quick_job_runs_the_quick_checks(tmp_path: Path) -> None:
    held = Entry(VariantId("0123456789abcdef"), tmp_path, b"brep", "b" * 64)
    table = load_materials()
    plan = jobs.plan(tmp_path, held, build_request("prusament-pla", table), table, {})
    assert (plan.quick.checks, plan.quick.budget, plan.background) == (QUICK, Quick(), ())
    assert "fea" not in [spec.id for spec in QUICK]


def test_each_demanded_load_case_is_one_fea_job_sent_only_what_fea_takes(tmp_path: Path) -> None:
    plan = background_plan(tmp_path)
    (job,) = plan.background
    assert (job.checks, job.budget, job.instance) == ((FEA,), FEA.budget, "c1")
    assert job.request.wire["checks"] == ["fea"]
    assert job.request.wire["load_cases"] == [CASE]
    assert set(job.request.wire["values"]) == set(FEA.takes)
    assert plan.quick.request.wire["load_cases"] == []
    assert job.key != plan.quick.key


def test_a_finished_fea_job_fills_its_place_with_its_instance(tmp_path: Path) -> None:
    (solved,) = unknown_for_all("solved", (FEA,))
    done = Done(
        JobResult(
            check_image_digest="sha256:" + "i" * 64,
            step=StepMissing(reason=jobs.NO_STEP),
            results=(solved.model_copy(update={"instance": "c1"}),),
        )
    )
    card, _ = assembled(tmp_path, done)
    assert card.pending == ()
    assert (card.finished[4].check_id, card.finished[4].instance) == ("fea", "c1")
    assert '"instance": "c1"' in card.model_dump_json(indent=1)
    assert '"instance"' not in card.finished[0].model_dump_json()
