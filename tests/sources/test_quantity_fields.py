import pytest

from cad.sources.fields import Field
from cad.sources.quantities import Quantity, Reason, Refusal, one_quantity


@pytest.mark.parametrize(
    ("quote", "field", "canonical"),
    [
        ("Poisson's ratio 0.36", "poisson_ratio", 0.36),
        ("Poisson\u2019s Ratio 0.33", "poisson_ratio", 0.33),
        ("Young's modulus 3.5 GPa", "elastic_modulus", 3500.0),
        ("Tensile Modulus 2346 MPa", "elastic_modulus", 2346.0),
        ("Tensile Strength at Yield 48 MPa", "yield_strength", 48.0),
        ("Tensile strength 50 MPa", "tensile_strength", 50.0),
        ("Yield strength 7250 psi", "yield_strength", 49.99),
        ("Tensile strength 60 N/mm2", "tensile_strength", 60.0),
    ],
)
def test_the_reader_reads_the_mechanical_fields(quote: str, field: Field, canonical: float) -> None:
    read = one_quantity(quote, field)
    assert isinstance(read, Quantity)
    assert read.canonical == pytest.approx(canonical, rel=1e-3)


@pytest.mark.parametrize(
    ("quote", "field", "reason"),
    [
        ("0.36", "poisson_ratio", Reason.NO_LABEL),
        ("Poisson's ratio 0.36 MPa", "poisson_ratio", Reason.WRONG_DIMENSION),
        ("Poisson's ratio 0.7", "poisson_ratio", Reason.OUT_OF_BAND),
        ("Tensile strength 50 MPa", "yield_strength", Reason.OTHER_QUANTITY),
        ("Flexural modulus 3.1 GPa", "elastic_modulus", Reason.UNRECOGNISED_TEXT),
        ("Young's modulus 3.5 g/cm3", "elastic_modulus", Reason.UNKNOWN_UNIT),
    ],
)
def test_the_reader_refuses_what_is_not_one_value_of_the_field(
    quote: str, field: Field, reason: Reason
) -> None:
    read = one_quantity(quote, field)
    assert isinstance(read, Refusal)
    assert read.reason == reason
