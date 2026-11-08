import hashlib
import typing
from dataclasses import replace
from functools import cache
from pathlib import Path

import pint
import pytest
from binding import bind
from provenance import (
    CardTrace,
    CheckStep,
    Incomplete,
    Resolved,
    Stale,
    TableStep,
    Unresolved,
    trace_card,
)
from trace_store import SPEC_BY_ID, Tally, exit_code, main, tally
from tracking import NO_REQUIREMENTS, NoRequirements, describe, outcomes_of, track

from cad.checks.report import SPECS, CheckSpec
from cad.checks.result import CheckResult, Measure, Measured, StepMissing, StepStored, Verdict
from cad.sandbox.outcome import Build, Built, NoResult
from cad.scorecard.model import Scorecard
from cad.scorecard.score import SCORECARD
from cad.tables.materials import UNITS, Cited, MaterialsTable, Unknown, load_materials
from cad.variants import entry

KEY = "prusament-pla"
VARIANT_ID = "0123456789abcdef"
BREP = b"BREP"
STEP = b"STEP"
BREP_SHA = hashlib.sha256(BREP).hexdigest()
STEP_SHA = hashlib.sha256(STEP).hexdigest()


@cache
def table() -> MaterialsTable:
    return load_materials()


def table_number(field: str, unit: str) -> pint.Quantity:
    cited = getattr(table().get_material(KEY), field)
    assert isinstance(cited, Cited)
    return UNITS.Quantity(cited.magnitude_in(unit), unit)


def measures_of(spec: CheckSpec) -> tuple[Measure, ...]:
    return tuple(
        Measure(
            name=name,
            value=table_number(spec.reads[name], unit)
            if name in spec.reads
            else UNITS.Quantity(1.0, unit),
        )
        for name, unit in spec.measures.items()
    )


def genuine_result(spec: CheckSpec) -> CheckResult:
    rows = tuple(getattr(table().get_material(KEY), field).source for field in spec.reads.values())
    return CheckResult(
        check_id=spec.id,
        verdict=Verdict.PASS,
        measured=measures_of(spec),
        formula=spec.formula,
        reason="ok",
        sources=(*spec.sources, *rows),
        version=spec.version,
    )


def genuine_card(**changes: object) -> Scorecard:
    card = Scorecard(
        variant_id=VARIANT_ID,
        material_key=KEY,
        table_version=table().version,
        image_digest="sha256:" + "i" * 64,
        brep_sha256=BREP_SHA,
        step=StepStored(sha256=STEP_SHA),
        results=tuple(genuine_result(spec) for spec in SPECS),
    )
    return card.model_copy(update=changes)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    root = tmp_path / "store"
    root.mkdir()
    entry.save(
        root, entry.VariantId(VARIANT_ID), "x = 1\n", Build(outcome=Built(), output=""), BREP
    )
    (root / VARIANT_ID / entry.STEP).write_bytes(STEP)
    return root


def trace(card: Scorecard, root: Path) -> CardTrace:
    return trace_card(card, root, table(), SPEC_BY_ID)


def with_result(card: Scorecard, check_id: str, **changes: object) -> Scorecard:
    results = tuple(
        result.model_copy(update=changes) if result.check_id == check_id else result
        for result in card.results
    )
    return card.model_copy(update={"results": results})


def result_of(card: Scorecard, check_id: str) -> CheckResult:
    return next(result for result in card.results if result.check_id == check_id)


def reasons(traced: CardTrace, kind: type[Stale] | type[Unresolved], label: str = "") -> list[str]:
    return [
        one.outcome.reason
        for one in traced.numbers
        if isinstance(one.outcome, kind) and one.label.startswith(label)
    ]


def test_a_genuine_scorecard_resolves_every_number_and_has_no_failure(store: Path) -> None:
    traced = trace(genuine_card(), store)
    assert traced.numbers
    assert traced.failures == ()
    assert all(isinstance(one.outcome, Resolved) for one in traced.numbers)


def test_a_computed_number_resolves_to_its_check_at_the_version_that_ran(store: Path) -> None:
    volume = next(one for one in trace(genuine_card(), store).numbers if one.label == "mass.volume")
    assert volume.outcome == Resolved((CheckStep("mass", SPEC_BY_ID["mass"].version),))


def test_a_density_walks_from_the_check_to_the_table_row_and_its_source(store: Path) -> None:
    traced = trace(genuine_card(), store)
    density = next(one for one in traced.numbers if one.label == "mass.density")
    assert isinstance(density.outcome, Resolved)
    check, row = density.outcome.steps
    assert isinstance(check, CheckStep) and check.check_id == "mass"
    assert isinstance(row, TableStep)
    assert (row.material_key, row.field) == (KEY, "density")
    cited = table().get_material(KEY).density
    assert isinstance(cited, Cited)
    assert row.source == cited.source


def test_every_check_declaring_a_read_is_traced_to_its_row_without_naming_the_check(
    store: Path,
) -> None:
    reading = {spec.id: spec for spec in SPECS if spec.reads}
    assert reading
    for one in trace(genuine_card(), store).numbers:
        check_id, _, name = one.label.partition(".")
        expected = check_id in reading and name in reading[check_id].reads
        assert isinstance(one.outcome, Resolved)
        assert any(isinstance(step, TableStep) for step in one.outcome.steps) == expected


def test_a_hand_edited_density_does_not_match_its_table_row(store: Path) -> None:
    mass = result_of(genuine_card(), "mass")
    edited = tuple(
        Measure(name=one.name, value=UNITS.Quantity(2.5e-6, "kg/mm^3"))
        if one.name == "density"
        else one
        for one in mass.measured
    )
    failures = reasons(
        trace(with_result(genuine_card(), "mass", measured=edited), store), Unresolved
    )
    assert len(failures) == 1
    assert "prusament-pla density" in failures[0]


def test_a_density_result_without_the_row_source_does_not_resolve(store: Path) -> None:
    card = with_result(genuine_card(), "mass", sources=SPEC_BY_ID["mass"].sources)
    assert "does not carry the density source" in reasons(trace(card, store), Unresolved)[0]


def test_a_density_the_table_marks_unknown_cannot_resolve(store: Path) -> None:
    real = table().get_material(KEY)
    unknown = MaterialsTable(table().version, {KEY: replace(real, density=Unknown())})
    traced = trace_card(genuine_card(), store, unknown, SPEC_BY_ID)
    assert "says unknown" in reasons(traced, Unresolved)[0]


def test_a_material_key_the_table_lacks_cannot_resolve(store: Path) -> None:
    card = genuine_card(material_key="unobtainium")
    assert "no row 'unobtainium'" in reasons(trace(card, store), Unresolved)[0]


def test_a_stale_check_version_is_stale_for_its_numbers_only(store: Path) -> None:
    traced = trace(with_result(genuine_card(), "mass", version="0" * 64), store)
    assert reasons(traced, Stale, "mass.")
    assert not reasons(traced, Unresolved)
    assert not [
        one
        for one in traced.numbers
        if isinstance(one.outcome, Stale) and not one.label.startswith("mass.")
    ]


def test_a_stale_materials_table_makes_the_density_stale(store: Path) -> None:
    traced = trace(genuine_card(table_version="0" * 64), store)
    stale = [one.label for one in traced.numbers if isinstance(one.outcome, Stale)]
    assert stale == ["mass.density"]


def test_a_measure_the_check_does_not_declare_is_unresolved(store: Path) -> None:
    mass = result_of(genuine_card(), "mass")
    extra = Measure(name="safety_factor", value=UNITS.Quantity(9.0, "dimensionless"))
    card = with_result(genuine_card(), "mass", measured=(*mass.measured, extra))
    assert reasons(trace(card, store), Unresolved) == [
        "mass does not declare a measure called 'safety_factor'"
    ]


def test_a_measure_in_another_unit_is_unresolved(store: Path) -> None:
    mass = result_of(genuine_card(), "mass")
    grams = tuple(
        Measure(name=one.name, value=UNITS.Quantity(1.0, "g")) if one.name == "mass" else one
        for one in mass.measured
    )
    failures = reasons(
        trace(with_result(genuine_card(), "mass", measured=grams), store), Unresolved
    )
    assert len(failures) == 1
    assert "not kg" in failures[0]


def test_a_number_from_a_check_that_is_not_registered_is_unresolved(store: Path) -> None:
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
    traced = trace(card.model_copy(update={"results": (*card.results, forged)}), store)
    assert reasons(traced, Unresolved, "oracle") == ["no check called 'oracle' is registered"]
    assert any("oracle, which is not a registered check" in f.reason for f in traced.failures)


class Padded(Scorecard):
    confidence: float = 0.9
    attempts: int = 3
    tolerance: Measured = UNITS.Quantity(0.1, "mm")


def test_a_number_that_no_rule_places_is_unresolved(store: Path) -> None:
    card = Padded(**genuine_card().model_dump())
    unplaced = reasons(trace(card, store), Unresolved)
    assert sorted(unplaced) == [
        "no rule places a number at attempts",
        "no rule places a number at confidence",
        "no rule places a number at tolerance",
    ]


def test_the_scorecard_declares_no_bare_numeric_field() -> None:
    def numeric(annotation: object) -> bool:
        if annotation is int or annotation is float:
            return True
        return any(numeric(part) for part in typing.get_args(annotation))

    bare = [name for name, field in Scorecard.model_fields.items() if numeric(field.annotation)]
    assert bare == []


def test_a_card_with_no_results_is_incomplete_with_no_number(store: Path) -> None:
    traced = trace(genuine_card(results=()), store)
    assert Incomplete("the card has no results") in traced.failures
    assert Incomplete("the card holds no number") in traced.failures


def test_a_card_missing_a_registered_check_is_incomplete(store: Path) -> None:
    card = genuine_card()
    kept = tuple(result for result in card.results if result.check_id != "mass")
    traced = trace(card.model_copy(update={"results": kept}), store)
    assert Incomplete("no result for the registered check mass") in traced.failures
    assert all(isinstance(one.outcome, Resolved) for one in traced.numbers)


def test_a_card_with_a_check_twice_is_incomplete(store: Path) -> None:
    card = genuine_card()
    twice = (*card.results, result_of(card, "extents"))
    traced = trace(card.model_copy(update={"results": twice}), store)
    assert Incomplete("2 results for extents") in traced.failures


def test_a_card_whose_results_measure_nothing_is_incomplete(store: Path) -> None:
    card = genuine_card()
    emptied = tuple(result.model_copy(update={"measured": ()}) for result in card.results)
    traced = trace(card.model_copy(update={"results": emptied}), store)
    assert traced.failures == (Incomplete("the card holds no number"),)


def test_a_card_is_bound_to_the_shape_the_signed_build_stored(store: Path) -> None:
    assert bind(store, genuine_card()) is None
    unbound = bind(store, genuine_card(brep_sha256="f" * 64))
    assert unbound is not None and "the signed build stored" in unbound.reason


def test_a_card_with_no_build_record_is_unbound(tmp_path: Path) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    (tmp_path / "bare.key").write_bytes(b"k" * 32)
    (tmp_path / "bare.key").chmod(0o600)
    unbound = bind(root, genuine_card())
    assert unbound is not None and "no build record" in unbound.reason


def test_a_variant_directory_with_no_signed_record_is_unbound(tmp_path: Path) -> None:
    root = tmp_path / "unsigned"
    (root / VARIANT_ID).mkdir(parents=True)
    (tmp_path / "unsigned.key").write_bytes(b"k" * 32)
    (tmp_path / "unsigned.key").chmod(0o600)
    unbound = bind(root, genuine_card())
    assert unbound is not None and "did not sign" in unbound.reason


def test_a_store_without_a_key_is_unbound_and_no_key_is_made(tmp_path: Path) -> None:
    root = tmp_path / "keyless"
    root.mkdir()
    unbound = bind(root, genuine_card())
    assert unbound is not None and "no key" in unbound.reason
    assert not (tmp_path / "keyless.key").exists()


def test_a_build_record_the_store_did_not_sign_is_unbound(store: Path) -> None:
    manifest = store / VARIANT_ID / entry.MANIFEST
    manifest.write_bytes(manifest.read_bytes().replace(BREP_SHA.encode(), b"f" * 64))
    unbound = bind(store, genuine_card(brep_sha256="f" * 64))
    assert unbound is not None and "did not sign" in unbound.reason


def test_a_build_without_a_shape_is_unbound(tmp_path: Path) -> None:
    root = tmp_path / "failed"
    root.mkdir()
    failed = Build(outcome=NoResult(reason="r"), output="")
    entry.save(root, entry.VariantId(VARIANT_ID), "x\n", failed, None)
    unbound = bind(root, genuine_card())
    assert unbound is not None and "without a shape" in unbound.reason


def test_a_stored_step_must_hash_to_the_one_on_the_card(store: Path) -> None:
    (store / VARIANT_ID / entry.STEP).write_bytes(b"another STEP")
    unbound = bind(store, genuine_card())
    assert unbound is not None and "names STEP" in unbound.reason


def test_a_stored_step_that_is_gone_is_unbound(store: Path) -> None:
    (store / VARIANT_ID / entry.STEP).unlink()
    unbound = bind(store, genuine_card())
    assert unbound is not None and "cannot be read" in unbound.reason


def test_a_card_with_no_step_needs_none_on_disk(store: Path) -> None:
    (store / VARIANT_ID / entry.STEP).unlink()
    assert bind(store, genuine_card(step=StepMissing(reason="none"))) is None


def put(root: Path, card: Scorecard | str) -> None:
    text = card if isinstance(card, str) else card.model_dump_json(indent=2) + "\n"
    (root / VARIANT_ID / SCORECARD).write_text(text)


def lines(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out


def test_the_command_passes_on_a_store_of_genuine_scorecards(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(store, genuine_card())
    assert main(["--root", str(store)]) == 0
    out = lines(capsys)
    assert "cards unreadable: 0, unbound: 0, incomplete: 0" in out
    count = len(trace(genuine_card(), store).numbers)
    assert f"numbers resolved: {count}, stale: 0, unresolved: 0" in out
    assert "strict pass rate: no requirements" in out


def test_the_command_prints_the_chain_of_a_computed_number(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(store, genuine_card())
    assert main(["--root", str(store), "--steps"]) == 0
    out = lines(capsys)
    assert "mass.volume = " in out
    assert f"computed by check mass at version {SPEC_BY_ID['mass'].version[:12]}" in out
    assert "table prusament-pla.density" in out


def test_the_command_counts_each_kind_of_failure_on_its_own(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(store, with_result(genuine_card(brep_sha256="f" * 64, results=()), "mass"))
    assert main(["--root", str(store)]) == 1
    out = lines(capsys)
    assert "cards unreadable: 0, unbound: 1, incomplete: 1" in out


def test_the_command_fails_on_an_unreadable_scorecard(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(store, '{"variant_id": "0123456789abcdef"}')
    assert main(["--root", str(store)]) == 1
    out = lines(capsys)
    assert "UNREADABLE" in out
    assert "cards unreadable: 1, unbound: 0, incomplete: 0" in out


def test_the_command_fails_on_a_card_stored_under_another_variant_id(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(store, genuine_card(variant_id="fedcba9876543210"))
    assert main(["--root", str(store)]) == 1
    assert "stored under" in lines(capsys)


def test_the_command_fails_on_a_store_with_no_scorecard(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path)]) == 1


def test_stale_and_unresolved_numbers_are_counted_apart(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    card = with_result(genuine_card(), "extents", version="0" * 64)
    put(store, card.model_copy(update={"material_key": "unobtainium"}))
    assert main(["--root", str(store)]) == 1
    out = lines(capsys)
    assert "stale: 2, unresolved: 1" in out


COUNTS = Tally(
    cards=1, unreadable=0, unbound=0, incomplete=0, numbers=3, resolved=3, stale=0, unresolved=0
)


@pytest.mark.parametrize(
    ("counts", "code"),
    [
        (COUNTS, 0),
        (replace(COUNTS, cards=0), 1),
        (replace(COUNTS, numbers=0, resolved=0), 1),
        (replace(COUNTS, unreadable=1), 1),
        (replace(COUNTS, unbound=1), 1),
        (replace(COUNTS, incomplete=1), 1),
        (replace(COUNTS, stale=1, resolved=2), 1),
        (replace(COUNTS, unresolved=1, resolved=2), 1),
    ],
)
def test_one_function_decides_the_exit_code(counts: Tally, code: int) -> None:
    assert exit_code(counts) == code


def test_the_tally_counts_a_card_once_per_kind_of_failure() -> None:
    traced = CardTrace("a" * 16, (Incomplete("x"), Incomplete("y")), ())
    assert tally([traced]).incomplete == 1


def test_scorecards_without_requirements_report_no_requirements_and_do_not_divide() -> None:
    tracking = track(outcomes_of(genuine_card()))
    assert tracking.strict_pass_rate == NoRequirements()
    assert tracking.reviewed_coverage == NoRequirements()
    assert describe(tracking.strict_pass_rate) == NO_REQUIREMENTS
