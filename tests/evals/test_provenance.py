from collections.abc import Mapping
from dataclasses import replace
from functools import cache
from pathlib import Path

import pint
import pytest
from provenance import (
    TABLE_READS,
    CheckStep,
    Resolved,
    TableStep,
    Traced,
    Unresolved,
    trace_card,
)
from trace_store import SPEC_BY_ID, main
from tracking import NO_REQUIREMENTS, NoRequirements, describe, outcomes_of, track

from cad.checks.report import SPECS, CheckSpec
from cad.checks.result import CheckResult, Measure, StepMissing, Verdict
from cad.scorecard.model import Scorecard
from cad.scorecard.score import SCORECARD
from cad.tables.materials import UNITS, Cited, MaterialsTable, Unknown, load_materials

KEY = "prusament-pla"
VARIANT_ID = "0123456789abcdef"


@cache
def table() -> MaterialsTable:
    return load_materials()


def table_number(field: str) -> pint.Quantity:
    cited = getattr(table().get_material(KEY), field)
    assert isinstance(cited, Cited)
    return UNITS.Quantity(cited.magnitude_in("kg/mm^3"), "kg/mm^3")


def measures_of(spec: CheckSpec) -> tuple[Measure, ...]:
    return tuple(
        Measure(
            name=name,
            value=table_number(TABLE_READS[spec.id, name])
            if (spec.id, name) in TABLE_READS
            else UNITS.Quantity(1.0, unit),
        )
        for name, unit in spec.measures.items()
    )


def genuine_result(spec: CheckSpec) -> CheckResult:
    datasheet = tuple(
        getattr(table().get_material(KEY), field).source
        for check_id, field in TABLE_READS.items()
        if check_id[0] == spec.id
    )
    return CheckResult(
        check_id=spec.id,
        verdict=Verdict.PASS,
        measured=measures_of(spec),
        formula=spec.formula,
        reason="ok",
        sources=(*spec.sources, *datasheet),
        version=spec.version,
    )


def genuine_card() -> Scorecard:
    return Scorecard(
        variant_id=VARIANT_ID,
        material_key=KEY,
        table_version=table().version,
        image_digest="sha256:" + "i" * 64,
        brep_sha256="b" * 64,
        step=StepMissing(reason="test"),
        results=tuple(genuine_result(spec) for spec in SPECS),
    )


def with_result(card: Scorecard, check_id: str, **changes: object) -> Scorecard:
    results = tuple(
        replace_result(result, **changes) if result.check_id == check_id else result
        for result in card.results
    )
    return card.model_copy(update={"results": results})


def replace_result(result: CheckResult, **changes: object) -> CheckResult:
    return result.model_copy(update=changes)


def trace(card: Scorecard) -> tuple[Traced, ...]:
    return trace_card(card, table(), SPEC_BY_ID)


def reasons(traced: tuple[Traced, ...], check_id: str) -> list[str]:
    return [
        one.outcome.reason
        for one in traced
        if one.check_id == check_id and isinstance(one.outcome, Unresolved)
    ]


def test_a_genuine_scorecard_resolves_every_number() -> None:
    traced = trace(genuine_card())
    assert traced
    assert all(isinstance(one.outcome, Resolved) for one in traced)


def test_a_density_walks_from_the_check_to_the_table_row_and_its_source() -> None:
    density = next(one for one in trace(genuine_card()) if one.name == "density")
    assert isinstance(density.outcome, Resolved)
    check, row = density.outcome.steps
    assert isinstance(check, CheckStep) and check.check_id == "mass"
    assert isinstance(row, TableStep)
    assert (row.material_key, row.field) == (KEY, "density")
    assert row.source == table().get_material(KEY).density.source  # pyright: ignore[reportAttributeAccessIssue]


def test_a_measured_geometry_number_stops_at_the_check_and_its_cited_source() -> None:
    volume = next(one for one in trace(genuine_card()) if one.name == "volume")
    assert isinstance(volume.outcome, Resolved)
    (check,) = volume.outcome.steps
    assert isinstance(check, CheckStep)
    assert check.sources == SPEC_BY_ID["mass"].sources


def test_every_number_of_a_result_with_its_sources_removed_fails() -> None:
    card = with_result(genuine_card(), "mass", sources=())
    failures = reasons(trace(card), "mass")
    assert len(failures) == len(SPEC_BY_ID["mass"].measures)
    assert all("does not carry its cited source" in reason for reason in failures)


def test_a_hand_edited_density_does_not_match_its_table_row() -> None:
    card = genuine_card()
    mass = next(result for result in card.results if result.check_id == "mass")
    edited = tuple(
        Measure(name=one.name, value=UNITS.Quantity(2.5e-6, "kg/mm^3"))
        if one.name == "density"
        else one
        for one in mass.measured
    )
    failures = reasons(trace(with_result(card, "mass", measured=edited)), "mass")
    assert len(failures) == 1
    assert "prusament-pla density" in failures[0]


def test_a_density_the_table_marks_unknown_cannot_resolve() -> None:
    real = table().get_material(KEY)
    unknown = MaterialsTable(table().version, {KEY: replace(real, density=Unknown())})
    traced = trace_card(genuine_card(), unknown, SPEC_BY_ID)
    assert "says unknown" in reasons(traced, "mass")[0]


def test_a_material_key_the_table_lacks_cannot_resolve() -> None:
    card = genuine_card().model_copy(update={"material_key": "unobtainium"})
    assert "no row 'unobtainium'" in reasons(trace(card), "mass")[0]


def test_a_stale_check_version_fails_its_numbers_only() -> None:
    card = with_result(genuine_card(), "mass", version="0" * 64)
    traced = trace(card)
    assert reasons(traced, "mass")
    assert not any(reasons(traced, spec.id) for spec in SPECS if spec.id != "mass")


def test_a_stale_materials_table_fails_the_density_only() -> None:
    card = genuine_card().model_copy(update={"table_version": "0" * 64})
    failed = [one.name for one in trace(card) if isinstance(one.outcome, Unresolved)]
    assert failed == ["density"]


def test_a_measure_the_check_does_not_declare_fails() -> None:
    card = genuine_card()
    mass = next(result for result in card.results if result.check_id == "mass")
    extra = Measure(name="safety_factor", value=UNITS.Quantity(9.0, "dimensionless"))
    failures = reasons(trace(with_result(card, "mass", measured=(*mass.measured, extra))), "mass")
    assert failures == ["mass does not declare a measure called 'safety_factor'"]


def test_a_measure_in_another_unit_fails() -> None:
    card = genuine_card()
    mass = next(result for result in card.results if result.check_id == "mass")
    grams = tuple(
        Measure(name=one.name, value=UNITS.Quantity(1.0, "g")) if one.name == "mass" else one
        for one in mass.measured
    )
    failures = reasons(trace(with_result(card, "mass", measured=grams)), "mass")
    assert len(failures) == 1
    assert "not kg" in failures[0]


def test_a_number_from_a_check_that_is_not_registered_fails() -> None:
    card = genuine_card()
    forged = CheckResult(
        check_id="oracle",
        verdict=Verdict.PASS,
        measured=(Measure(name="score", value=UNITS.Quantity(1.0, "dimensionless")),),
        formula="trust me",
        reason="ok",
        sources=(),
        version="v",
    )
    traced = trace(card.model_copy(update={"results": (*card.results, forged)}))
    assert reasons(traced, "oracle") == ["no check called 'oracle' is registered"]


def test_a_check_that_cites_no_source_cannot_vouch_for_a_number() -> None:
    bare: Mapping[str, CheckSpec] = {
        spec.id: replace(spec, sources=()) for spec in SPEC_BY_ID.values()
    }
    traced = trace_card(genuine_card(), table(), bare)
    assert all(isinstance(one.outcome, Unresolved) for one in traced)


def store_with(root: Path, card: Scorecard | str) -> None:
    directory = root / VARIANT_ID
    directory.mkdir(parents=True)
    text = card if isinstance(card, str) else card.model_dump_json(indent=2) + "\n"
    (directory / SCORECARD).write_text(text)


def test_the_command_passes_on_a_store_of_genuine_scorecards(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_with(tmp_path, genuine_card())
    assert main(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "unresolved or unreadable: 0" in out
    assert "strict pass rate: no requirements" in out
    assert "requirements covered by reviewed checks: no requirements" in out


def test_the_command_fails_on_a_hand_edited_scorecard(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_with(tmp_path, with_result(genuine_card(), "mass", sources=()))
    assert main(["--root", str(tmp_path)]) == 1
    assert "UNRESOLVED mass.volume" in capsys.readouterr().out


def test_the_command_fails_on_an_unreadable_scorecard(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_with(tmp_path, '{"variant_id": "0123456789abcdef"}')
    assert main(["--root", str(tmp_path)]) == 1
    assert "UNREADABLE" in capsys.readouterr().out


def test_the_command_fails_on_a_store_with_no_scorecard(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path)]) == 1


def test_scorecards_without_requirements_report_no_requirements_and_do_not_divide() -> None:
    tracking = track(outcomes_of(genuine_card()))
    assert tracking.strict_pass_rate == NoRequirements()
    assert tracking.reviewed_coverage == NoRequirements()
    assert describe(tracking.strict_pass_rate) == NO_REQUIREMENTS
