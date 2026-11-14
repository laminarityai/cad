import pytest
from pydantic import ValidationError

from cad.checks.result import Measure
from cad.tables.materials import UNITS


@pytest.mark.parametrize(
    ("magnitude", "unit"),
    [(1.0, "nonsense_unit"), (1.0, "g/0"), (1.0, "(g"), (1.0, "g**"), (None, "g")],
)
def test_a_measure_that_cannot_be_read_as_a_quantity_is_a_validation_error(
    magnitude: object, unit: str
) -> None:
    with pytest.raises(ValidationError):
        Measure.model_validate({"name": "mass", "value": {"magnitude": magnitude, "unit": unit}})


def test_a_measure_with_a_known_unit_reads_as_that_quantity() -> None:
    measure = Measure.model_validate({"name": "mass", "value": {"magnitude": 2.0, "unit": "g"}})
    assert f"{measure.value:~P}" == "2.0 g"


def test_a_fault_in_the_unit_registry_is_raised_and_not_read_as_a_bad_measure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_: object) -> object:
        raise RecursionError("the unit registry recursed")

    monkeypatch.setattr(UNITS, "Quantity", broken)
    with pytest.raises(RecursionError):
        Measure.model_validate({"name": "mass", "value": {"magnitude": 2.0, "unit": "g"}})
