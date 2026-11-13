import pytest
from pydantic import ValidationError

from cad.checks.result import Measure


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
