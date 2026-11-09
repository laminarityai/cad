import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from cad.checks.report import IMAGE_TAG, unknown_for_all
from cad.checks.result import Comparator, StepMissing, Verdict
from cad.sandbox.image import BUILD, current_image, image_tag
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard import score
from cad.scorecard.model import (
    AgainstBrief,
    AwaitingConfirmation,
    Basis,
    Checked,
    Comparison,
    NoBrief,
    Scorecard,
    Unverified,
)
from cad.tables.materials import UNITS
from cad.variants import entry

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
PLATE_SHELL = PLATE + "from build123d import Shell\nresult = Shell(result.faces()[:-1])\n"
PLATE_VOLUME_MM3 = 29509.72
CHECK_IDS = ["closed_solid", "interference", "mass", "extents"]
UNBUILT_ID = "0123456789abcdef"

type Build = Callable[[str], str]


def stored(store: Path, variant_id: str) -> Scorecard:
    return Scorecard.model_validate_json((store / variant_id / score.SCORECARD).read_text())


def offline_card(basis: Basis | None = None) -> Scorecard:
    return Scorecard(
        variant_id=UNBUILT_ID,
        material_key="prusament-pla",
        table_version="t" * 64,
        check_image_digest="sha256:" + "i" * 64,
        brep_sha256="b" * 64,
        step=StepMissing(reason="offline"),
        results=unknown_for_all("offline"),
        basis=NoBrief() if basis is None else basis,
    )


LIGHT = Checked(
    requirement_id="a" * 16,
    statement="Mass at most 150 g",
    check_id="mass",
    verdict=Verdict.UNKNOWN,
    reason="r",
    comparisons=(
        Comparison(
            measure="mass",
            comparator=Comparator.AT_MOST,
            limit=UNITS.Quantity(150, "g"),
            verdict=Verdict.UNKNOWN,
        ),
    ),
)
SHELF = Unverified(requirement_id="b" * 16, statement="holds a shelf")
AGAINST = AgainstBrief(
    brief_id="1" * 16,
    decision_sha256="d" * 64,
    requirements=(LIGHT, SHELF),
    unverified_requirements=(SHELF.requirement_id,),
)


def test_the_plate_passes_every_check_with_its_volume(built: Build, store: Path) -> None:
    variant_id = built(PLATE)
    card = score.score_variant(variant_id, "prusament-pla", store)
    assert [result.check_id for result in card.finished] == CHECK_IDS
    assert [result.verdict for result in card.finished] == [Verdict.PASS] * 4
    assert card.finished[2].number("volume", "mm^3") == pytest.approx(PLATE_VOLUME_MM3, abs=0.01)


def test_the_scorecard_names_the_table_the_analysis_image_and_every_check_version(
    built: Build, store: Path
) -> None:
    card = score.score_variant(built(PLATE), "prusament-pla", store)
    assert len(card.table_version) == 64
    assert card.check_image_digest == current_image(IMAGE_TAG)
    assert card.check_image_digest != current_image(image_tag(BUILD))
    assert all(result.version and result.formula and result.sources for result in card.finished)
    fields = json.loads(card.model_dump_json())
    assert [result["version"] for result in fields["results"]] == [r.version for r in card.finished]


@pytest.mark.parametrize(
    "basis", [NoBrief(), AwaitingConfirmation(brief_id="1" * 16), AGAINST], ids=lambda b: b.kind
)
def test_a_card_with_each_basis_round_trips_through_its_stored_json(
    tmp_path: Path, basis: Basis
) -> None:
    card = offline_card(basis)
    (tmp_path / card.variant_id).mkdir()
    path = score.store(card, tmp_path)
    assert Scorecard.model_validate_json(path.read_text()) == card
    assert sorted(child.name for child in path.parent.iterdir()) == [score.SCORECARD]


@pytest.mark.parametrize(
    "listed", [(), (LIGHT.requirement_id,), (SHELF.requirement_id, SHELF.requirement_id)]
)
def test_unverified_requirements_must_list_exactly_the_unverified_entries(
    listed: tuple[str, ...],
) -> None:
    with pytest.raises(ValidationError, match="unverified_requirements"):
        AGAINST.model_validate({**AGAINST.model_dump(), "unverified_requirements": listed})


def test_a_phase_one_card_with_a_requirements_note_and_no_basis_is_unreadable() -> None:
    old = offline_card().model_dump(mode="json")
    del old["basis"]
    old["unverified_requirements"] = []
    old["requirements_note"] = "Phase 1 reads no requirements from the brief."
    with pytest.raises(ValidationError):
        Scorecard.model_validate(old)


def test_scoring_gives_the_basis_the_assessor_gives_for_the_suite_it_ran(
    built: Build, store: Path
) -> None:
    seen: list[score.Results] = []

    def awaiting(results: score.Results) -> Basis:
        seen.append(results)
        return AwaitingConfirmation(brief_id="1" * 16)

    variant_id = built(PLATE)
    card = score.score_variant(variant_id, "prusament-pla", store, awaiting)
    assert seen == [card.results]
    assert card.basis == AwaitingConfirmation(brief_id="1" * 16)
    assert score.score_variant(variant_id, "prusament-pla", store).basis == NoBrief()


def test_the_plate_shell_mutant_is_scored_with_closed_solid_failed(
    built: Build, store: Path
) -> None:
    card = score.score_variant(built(PLATE_SHELL), "prusament-pla", store)
    assert card.finished[0].verdict == Verdict.FAIL
    assert card.finished[2].verdict == Verdict.UNKNOWN
    assert card.finished[2].measured == ()


def test_an_unknown_material_key_is_scored_with_mass_unknown(built: Build, store: Path) -> None:
    variant_id = built(PLATE)
    card = score.score_variant(variant_id, "unobtainium", store)
    assert [result.verdict for result in card.finished] == [
        Verdict.PASS,
        Verdict.PASS,
        Verdict.UNKNOWN,
        Verdict.PASS,
    ]


def test_an_edited_scorecard_file_changes_nothing_the_next_score_reports(
    built: Build, store: Path
) -> None:
    variant_id = built(PLATE_SHELL)
    honest = score.score_variant(variant_id, "prusament-pla", store)
    path = score.store(honest, store)
    path.write_text(path.read_text().replace('"fail"', '"pass"'))
    assert stored(store, variant_id) != honest
    assert score.score_variant(variant_id, "prusament-pla", store) == honest


def test_an_unknown_variant_is_refused_naming_the_id_and_stores_nothing(
    built: Build, store: Path
) -> None:
    built(PLATE)
    with pytest.raises(entry.UnknownVariant, match=UNBUILT_ID):
        score.score_variant(UNBUILT_ID, "prusament-pla", store)
    assert not (store / UNBUILT_ID).exists()


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
