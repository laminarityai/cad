import typing
from dataclasses import replace
from pathlib import Path

from chain import CheckStep, Resolved, Stale, TableStep, Unresolved
from provenance import trace_card
from trace_store import SPEC_BY_ID

from cad.checks.report import SPECS
from cad.checks.result import CheckResult, Measure, Measured, Verdict
from cad.scorecard.model import Scorecard
from cad.tables.materials import UNITS, Known, MaterialsTable, Unknown
from tests.support.cards import (
    KEY,
    genuine_card,
    reasons,
    result_of,
    roots_beside,
    table,
    trace,
    with_result,
)


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
    assert isinstance(cited, Known)
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
    traced = trace_card(genuine_card(), store, roots_beside(store), unknown, SPEC_BY_ID, None)
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
