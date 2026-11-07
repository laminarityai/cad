import json
from collections.abc import Callable
from pathlib import Path

import pytest

from cad.checks.report import unknown_for_all
from cad.checks.result import CheckRun, Verdict
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard import score
from cad.scorecard.model import NO_REQUIREMENTS_NOTE, Scorecard
from cad.variants import entry

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
PLATE_SHELL = PLATE + "from build123d import Shell\nresult = Shell(result.faces()[:-1])\n"
PLATE_VOLUME_MM3 = 29509.72
CHECK_IDS = ["closed_solid", "interference", "mass"]
UNBUILT_ID = "0123456789abcdef"

type Build = Callable[[str], str]


def stored(store: Path, variant_id: str) -> Scorecard:
    return Scorecard.model_validate_json((store / variant_id / score.SCORECARD).read_text())


def offline_run() -> CheckRun:
    return CheckRun(
        variant_id=UNBUILT_ID,
        material_key="prusament-pla",
        table_version="t" * 64,
        image_tag="cad-sandbox:0",
        image_digest="sha256:" + "i" * 64,
        brep_sha256="b" * 64,
        step_sha256=None,
        results=unknown_for_all("offline"),
    )


def offline_card() -> Scorecard:
    return score.scorecard_of(offline_run())


def test_the_plate_scorecard_equals_the_one_stored_beside_the_variant(
    built: Build, store: Path
) -> None:
    variant_id = built(PLATE)
    card = score.score_variant(variant_id, "prusament-pla", store)
    assert [result.check_id for result in card.results] == CHECK_IDS
    assert [result.verdict for result in card.results] == [Verdict.PASS] * 3
    assert card.results[2].number("volume", "mm^3") == pytest.approx(PLATE_VOLUME_MM3, abs=0.01)
    assert stored(store, variant_id) == card


def test_the_scorecard_names_the_table_the_image_and_every_check_version(
    built: Build, store: Path
) -> None:
    card = score.score_variant(built(PLATE), "prusament-pla", store)
    assert len(card.table_version) == 64
    assert card.image_digest.startswith("sha256:")
    assert all(result.version and result.formula and result.sources for result in card.results)
    fields = json.loads((store / card.variant_id / score.SCORECARD).read_text())
    assert [result["version"] for result in fields["results"]] == [r.version for r in card.results]


def test_the_scorecard_says_it_lists_no_requirements() -> None:
    card = offline_card()
    assert card.unverified_requirements == ()
    assert card.requirements_note == NO_REQUIREMENTS_NOTE
    assert "says nothing about whether the variant meets the brief" in card.requirements_note


def test_scoring_the_same_variant_twice_gives_equal_scorecards(built: Build, store: Path) -> None:
    variant_id = built(PLATE)
    first = score.score_variant(variant_id, "prusament-pla", store)
    second = score.score_variant(variant_id, "prusament-pla", store)
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_the_plate_shell_mutant_is_stored_with_closed_solid_failed(
    built: Build, store: Path
) -> None:
    variant_id = built(PLATE_SHELL)
    score.score_variant(variant_id, "prusament-pla", store)
    card = stored(store, variant_id)
    assert card.results[0].verdict == Verdict.FAIL
    assert card.results[2].verdict == Verdict.UNKNOWN
    assert card.results[2].measured == ()


def test_an_unknown_material_key_is_stored_with_mass_unknown(built: Build, store: Path) -> None:
    variant_id = built(PLATE)
    card = score.score_variant(variant_id, "unobtainium", store)
    assert [result.verdict for result in card.results] == [
        Verdict.PASS,
        Verdict.PASS,
        Verdict.UNKNOWN,
    ]
    assert stored(store, variant_id) == card


def test_an_edited_scorecard_file_changes_nothing_the_next_score_reports(
    built: Build, store: Path
) -> None:
    variant_id = built(PLATE_SHELL)
    honest = score.score_variant(variant_id, "prusament-pla", store)
    path = store / variant_id / score.SCORECARD
    path.write_text(path.read_text().replace('"fail"', '"pass"'))
    assert stored(store, variant_id) != honest
    assert score.score_variant(variant_id, "prusament-pla", store) == honest
    assert stored(store, variant_id) == honest


def test_an_unknown_variant_is_refused_naming_the_id_and_stores_nothing(
    built: Build, store: Path
) -> None:
    built(PLATE)
    with pytest.raises(entry.UnknownVariant, match=UNBUILT_ID):
        score.score_variant(UNBUILT_ID, "prusament-pla", store)
    assert not (store / UNBUILT_ID).exists()


def test_the_scorecard_round_trips_through_its_json(tmp_path: Path) -> None:
    card = offline_card()
    (tmp_path / card.variant_id).mkdir()
    path = score.store(card, tmp_path)
    assert Scorecard.model_validate_json(path.read_text()) == card
    assert sorted(child.name for child in path.parent.iterdir()) == [score.SCORECARD]


def test_a_symlinked_variant_directory_is_not_written_through(tmp_path: Path) -> None:
    card = offline_card()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / card.variant_id).symlink_to(elsewhere)
    with pytest.raises(SandboxUnavailable, match="cannot store"):
        score.store(card, root)
    assert list(elsewhere.iterdir()) == []


def test_a_directory_that_cannot_be_written_is_unavailable_and_leaves_no_temporary_file(
    tmp_path: Path,
) -> None:
    card = offline_card()
    directory = tmp_path / card.variant_id
    directory.mkdir()
    (directory / score.SCORECARD).mkdir()
    with pytest.raises(SandboxUnavailable, match="cannot store"):
        score.store(card, tmp_path)
    assert sorted(child.name for child in directory.iterdir()) == [score.SCORECARD]


def test_a_store_failure_names_the_variant_and_the_kind_and_no_host_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    card = offline_card()
    directory = tmp_path / card.variant_id
    directory.mkdir()
    (directory / score.SCORECARD).mkdir()
    with pytest.raises(SandboxUnavailable) as refused:
        score.store(card, tmp_path)
    message = str(refused.value)
    assert card.variant_id in message
    assert "IsADirectoryError" in message
    assert str(tmp_path) not in message
    assert str(directory / score.SCORECARD) in caplog.text
