import pytest
from fakes import REPORT_CAP, FakeKernel, request

from cad.checks.container import mass
from cad.checks.container.inputs import WIRE_UNITS, Input, Inputs, Undeclared
from cad.checks.container.runner import run
from cad.checks.report import DEPENDENCIES, IMAGE_TAG, QUICK, build_request, specs
from cad.tables.materials import FIELD_UNITS, UNITS, load_materials


def test_every_input_names_a_table_field_and_converts_to_its_wire_unit() -> None:
    assert set(WIRE_UNITS) == set(Input)
    for wanted, unit in WIRE_UNITS.items():
        assert UNITS.Unit(unit).dimensionality == UNITS.Unit(FIELD_UNITS[wanted]).dimensionality


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
    results = run(request(), b"brep", FakeKernel(), REPORT_CAP)["results"]
    found = next(result for result in results if result["id"] == "mass")
    assert (found["verdict"], found["reason"]) == (
        "unknown",
        "mass raised Undeclared: density is not in the check's TAKES",
    )


def test_the_runner_runs_the_named_checks_and_what_they_require() -> None:
    report = run(request(checks=("mass",)), b"brep", FakeKernel(), REPORT_CAP)
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
