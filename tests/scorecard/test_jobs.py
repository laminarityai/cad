from collections.abc import Callable
from pathlib import Path

import pytest

from cad.checks import job_store, jobs
from cad.checks.jobs import Background, JobResult, JobSpec, Plan, Quick, Refused
from cad.checks.lanes import Done, Pending, Settled
from cad.checks.report import SPECS, build_request, unknown_for_all
from cad.checks.result import CheckResult, StepMissing, Verdict
from cad.sandbox import container
from cad.sandbox.container import Job, Ran
from cad.scorecard import score
from cad.scorecard.model import Basis, NoBrief, PendingCheck, Scorecard
from cad.tables.materials import load_materials
from cad.variants.entry import Entry, VariantId

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
PLATE_SHELL = PLATE + "from build123d import Shell\nresult = Shell(result.faces()[:-1])\n"
MASS = SPECS[2]
FEA = Background(wall_seconds=600, memory_mb=2048, tmpfs_mb=768)

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
    request = build_request("prusament-pla", load_materials())
    quick = JobSpec(root, "0123456789abcdef", "b" * 64, SPECS, Quick(), request)
    fea = JobSpec(root, quick.variant_id, "b" * 64, (MASS,), FEA, request)
    return Plan(quick=quick, background=(fea,))


def quick_result() -> JobResult:
    return JobResult(
        check_image_digest="sha256:" + "i" * 64,
        step=StepMissing(reason="offline"),
        results=unknown_for_all("offline"),
    )


def assembled(root: Path, outcome: Done | Pending | Refused) -> tuple[Scorecard, list[str]]:
    seen: list[str] = []

    def assess(results: tuple[CheckResult, ...]) -> Basis:
        seen.extend(one.check_id for one in results)
        return NoBrief()

    plan = background_plan(root)
    request = plan.quick.request
    return score.scorecard_of(plan, request, Settled(quick_result(), (outcome,)), assess), seen


def test_a_pending_background_check_holds_its_place_and_no_verdict(tmp_path: Path) -> None:
    card, assessed = assembled(tmp_path, Pending())
    assert [one.check_id for one in card.results] == [spec.id for spec in SPECS]
    assert card.results[2] == PendingCheck(
        check_id="mass", formula=MASS.formula, sources=MASS.sources, version=MASS.version
    )
    assert card.pending == ("mass",)
    assert assessed == ["closed_solid", "interference", "extents"]
    assert Scorecard.model_validate_json(card.model_dump_json()) == card


def test_a_refused_background_check_is_unknown_with_the_reason(tmp_path: Path) -> None:
    card, _ = assembled(tmp_path, Refused("the account has no analysis time left"))
    assert card.pending == ()
    assert card.finished[2].verdict == Verdict.UNKNOWN
    assert card.finished[2].reason == "the account has no analysis time left"


def test_a_card_must_list_exactly_its_pending_checks(tmp_path: Path) -> None:
    card, _ = assembled(tmp_path, Pending())
    with pytest.raises(ValueError, match="pending must list"):
        Scorecard.model_validate({**card.model_dump(), "pending": []})


def test_today_one_quick_job_runs_every_check(tmp_path: Path) -> None:
    held = Entry(VariantId("0123456789abcdef"), tmp_path, b"brep", "b" * 64)
    request = build_request("prusament-pla", load_materials())
    plan = jobs.plan(tmp_path, held, request)
    assert (plan.quick.checks, plan.quick.budget, plan.background) == (SPECS, Quick(), ())
