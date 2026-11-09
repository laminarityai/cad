import pytest

from cad.sources.fields import Field
from cad.sources.quantities import Quantity, Reason, Refusal, one_quantity


@pytest.mark.parametrize(
    ("quote", "field", "canonical"),
    [
        ("a Poisson's ratio of 0.35 was used", "poisson_ratio", 0.35),
        ("the Poisson ratio = 0.36", "poisson_ratio", 0.36),
        ("The Poisson\u2019s ratio was taken as 0.33", "poisson_ratio", 0.33),
        ("0.36 was assumed as the Poisson's ratio", "poisson_ratio", 0.36),
        ("a Young's modulus of 3.5 GPa", "elastic_modulus", 3500.0),
        ("the yield strength was measured as 48 MPa", "yield_strength", 48.0),
        ("the density is equal to 1.24 g/cm3", "density", 1240.0),
    ],
)
def test_the_reader_reads_one_value_from_a_sentence_that_names_the_field(
    quote: str, field: Field, canonical: float
) -> None:
    read = one_quantity(quote, field)
    assert isinstance(read, Quantity)
    assert read.canonical == pytest.approx(canonical, rel=1e-3)


@pytest.mark.parametrize(
    ("quote", "field", "reason"),
    [
        ("a value of 0.35 was used", "poisson_ratio", Reason.NO_LABEL),
        ("1.24 g/cm3 was used", "density", Reason.NO_LABEL),
        ("the Poisson's ratio was reduced by 0.05", "poisson_ratio", Reason.UNRECOGNISED_TEXT),
        ("Poisson's ratio of pure PLA equals 0.35", "poisson_ratio", Reason.UNRECOGNISED_TEXT),
        (
            "a Poisson's ratio of 0.35 was used, 0.36 was found",
            "poisson_ratio",
            Reason.SEVERAL_QUANTITIES,
        ),
        ("a yield strength of 48 MPa was 50 MPa", "yield_strength", Reason.SEVERAL_QUANTITIES),
        ("Poisson's ratio 0.35a", "poisson_ratio", Reason.UNRECOGNISED_TEXT),
        ("Poisson's ratio 0.35as", "poisson_ratio", Reason.UNRECOGNISED_TEXT),
        ("a Poisson's ratio of at most 0.4", "poisson_ratio", Reason.BOUND),
        ("a Poisson's ratio of 0.3 to 0.35", "poisson_ratio", Reason.RANGE),
        ("the yield strength was 48 was used", "yield_strength", Reason.MISSING_UNIT),
        (
            "the yield strength was 48 MPa, the tensile strength was 50 MPa",
            "yield_strength",
            Reason.OTHER_QUANTITY,
        ),
    ],
)
def test_the_reader_refuses_a_sentence_that_is_not_one_value_of_the_field(
    quote: str, field: Field, reason: Reason
) -> None:
    read = one_quantity(quote, field)
    assert isinstance(read, Refusal)
    assert read.reason == reason
