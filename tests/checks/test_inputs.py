import pytest

from cad.checks.container import mass
from cad.checks.container.inputs import WIRE_UNITS, Input, Inputs, Undeclared
from cad.checks.report import DEPENDENCIES, IMAGE_TAG, QUICK, build_request, specs
from cad.tables.fields import FIELDS
from cad.tables.materials import UNITS, load_materials
from tests.support.check_fakes import FakeKernel, request, run_report


def test_every_input_names_a_table_field_and_converts_to_its_wire_unit() -> None:
    """The check image cannot import cad.tables, so inputs.py repeats the field names."""
    canonical: dict[str, str] = {field: spec.canonical_unit for field, spec in FIELDS.items()}
    assert set(WIRE_UNITS) == set(Input), "give every Input a unit in WIRE_UNITS in inputs.py"
    for wanted, unit in WIRE_UNITS.items():
        assert wanted in canonical, (
            f"Input.{wanted.name} is {wanted.value!r}, which is not a field in FIELDS. Make it"
            " match the field's name in cad/tables/fields.py, or add the field there."
        )
        assert UNITS.Unit(unit).dimensionality == UNITS.Unit(canonical[wanted]).dimensionality, (
            f"WIRE_UNITS[Input.{wanted.name}] is {unit!r}, which does not convert from"
            f" {canonical[wanted]!r}, the canonical unit of {wanted.value} in cad/tables/fields.py."
            " Fix the unit in cad/checks/container/inputs.py."
        )


def test_a_check_cannot_read_an_input_it_does_not_take() -> None:
    inputs = Inputs(
        frozenset({Input.DENSITY}), {Input.ELASTIC_MODULUS: {"kind": "known", "magnitude": 3500.0}}
    )
    with pytest.raises(Undeclared, match="elastic_modulus is not in the check's TAKES"):
        inputs.value(Input.ELASTIC_MODULUS)


def test_a_check_that_reads_an_input_it_does_not_take_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mass, "TAKES", frozenset[Input]())
    results = run_report(request(), b"brep", FakeKernel())[0]["results"]
    found = next(result for result in results if result["id"] == "mass")
    assert (found["verdict"], found["reason"]) == (
        "unknown",
        "mass raised Undeclared: density is not in the check's TAKES",
    )


def test_the_runner_runs_the_named_checks_and_what_they_require() -> None:
    report, _ = run_report(request(checks=("mass",)), b"brep", FakeKernel())
    assert [result["id"] for result in report["results"]] == [
        "closed_solid",
        "interference",
        "mass",
    ]


def test_a_check_that_echoes_an_input_it_does_not_take_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mass, "TAKES", frozenset[Input]())
    with pytest.raises(ValueError, match="mass reads an input it does not take"):
        specs(DEPENDENCIES, IMAGE_TAG)


def test_the_host_sends_only_the_values_the_checks_take() -> None:
    wire = build_request("prusament-pla", load_materials()).wire
    assert wire["checks"] == [spec.id for spec in QUICK]
    assert set(wire["values"]) == set().union(*(spec.takes for spec in QUICK)) == {Input.DENSITY}
