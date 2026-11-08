from pathlib import Path

import pytest

from cad.sandbox import container
from cad.sandbox.container import Job, Ran
from cad.sandbox.outcome import Build, Built, NoResult
from cad.scorecard import score
from cad.scorecard.model import Scorecard
from cad.variants import entry
from cad.variants.store import RebuildFailed, build_variant

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
OLD_TAG = "cad-sandbox:before-a-deploy"


def stored_by_an_older_sandbox(root: Path, code: str) -> entry.VariantId:
    vid = entry.variant_id(code, OLD_TAG)
    entry.save(root, vid, code, Build(outcome=Built(), output=""), b"an older shape")
    return vid


@pytest.fixture
def jobs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    real_run = container.run
    started: list[str] = []

    def run(job: Job) -> Ran:
        started.append(job.kind)
        return real_run(job)

    monkeypatch.setattr(container, "run", run)
    return started


def test_scoring_a_variant_an_older_sandbox_stored_scores_its_code_rebuilt(
    tmp_path: Path, jobs: list[str]
) -> None:
    old = stored_by_an_older_sandbox(tmp_path, PLATE)
    old_files = sorted(path.name for path in (tmp_path / old).iterdir())
    card = score.score_variant(old, "prusament-pla", tmp_path)
    assert jobs == ["build", "check"]
    assert card.rebuilt_from == old
    assert card.variant_id == build_variant(PLATE, tmp_path).variant_id != old
    stored = (tmp_path / card.variant_id / score.SCORECARD).read_text()
    assert Scorecard.model_validate_json(stored) == card
    assert sorted(path.name for path in (tmp_path / old).iterdir()) == old_files
    assert (tmp_path / old / entry.CODE).read_text() == PLATE


def test_scoring_the_older_variant_again_reuses_the_rebuild_and_its_checks(
    tmp_path: Path, jobs: list[str]
) -> None:
    old = stored_by_an_older_sandbox(tmp_path, PLATE)
    first = score.score_variant(old, "prusament-pla", tmp_path)
    jobs.clear()
    again = score.score_variant(old, "prusament-pla", tmp_path)
    assert jobs == []
    assert (again.variant_id, again.rebuilt_from) == (first.variant_id, old)


def test_an_older_variant_whose_build_failed_is_rebuilt_and_scored(
    tmp_path: Path, jobs: list[str]
) -> None:
    old = entry.variant_id(PLATE, OLD_TAG)
    failed = Build(outcome=NoResult(reason="the older sandbox found no result"), output="")
    entry.save(tmp_path, old, PLATE, failed, None)
    card = score.score_variant(old, "prusament-pla", tmp_path)
    assert jobs == ["build", "check"]
    assert (card.variant_id, card.rebuilt_from) == (build_variant(PLATE, tmp_path).variant_id, old)


def test_an_older_variant_whose_code_was_altered_is_refused_and_starts_no_container(
    tmp_path: Path, jobs: list[str]
) -> None:
    old = stored_by_an_older_sandbox(tmp_path, PLATE)
    (tmp_path / old / entry.CODE).write_text(PLATE + "result = result.scale(2)\n")
    with pytest.raises(entry.StaleVariant, match=f"variant {old} has a code.py that was altered"):
        score.score_variant(old, "prusament-pla", tmp_path)
    assert jobs == []


def test_a_rebuild_that_fails_reports_its_build_outcome_and_stores_no_scorecard(
    tmp_path: Path,
) -> None:
    code = "raise ValueError('a part this sandbox cannot build')\n"
    old = stored_by_an_older_sandbox(tmp_path, code)
    new = build_variant(code, tmp_path).variant_id
    with pytest.raises(RebuildFailed, match="build_failed") as raised:
        score.score_variant(old, "prusament-pla", tmp_path)
    assert f"variant {old}" in str(raised.value)
    assert f"as variant {new}" in str(raised.value)
    assert "a part this sandbox cannot build" in str(raised.value)
    assert not (tmp_path / old / score.SCORECARD).exists()
    assert not (tmp_path / new / score.SCORECARD).exists()
