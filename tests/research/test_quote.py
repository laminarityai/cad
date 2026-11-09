from decimal import Decimal

import pytest

from cad.research.quote import on_page, written_in


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("960 kg/m3", "Density: 8960 kg/m3"),
        ("1.34 g/cm3", "Density 11.34 g/cm3"),
        ("250 MPa", "Yield strength 1250 MPa"),
        ("Poisson's ratio 0.3", "Poisson's ratio 0.35"),
        ("Poisson's ratio 0", "Poisson's ratio 0.35"),
        ("34 g/cm3", "Density .34 g/cm3"),
        ("960 kg/m3", "Density 8,960 kg/m3"),
    ],
)
def test_a_quote_that_starts_or_ends_inside_a_number_is_not_on_the_page(
    quote: str, text: str
) -> None:
    assert not on_page(quote, text)


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("Density 8960 kg/m3", "Density 8960 kg/m3"),
        ("Poisson's ratio 0.35", "(Poisson's ratio 0.35)"),
        ("Poisson's ratio 0.35", "Poisson's ratio 0.35. Density 1.24 g/cm3"),
        ("Poisson's ratio 0.35", "Poisson's ratio 0.35, density 1.24 g/cm3"),
        ("Poisson's ratio 0.35", "Poisson's ratio 0.3 and Poisson's ratio 0.35"),
        ("DENSITY 1.21 G/CM3", "Density\u00a01.21 g/cm\u00b3"),
        ("Poisson\u2019s ratio 0.35", "Poisson's   ratio\n0.35"),
    ],
)
def test_a_quote_bounded_by_the_text_or_punctuation_is_on_the_page(quote: str, text: str) -> None:
    assert on_page(quote, text)


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("0.36", "the Poisson ratio = 0.36, was used"),
        ("0.36", "Poisson's ratio 0.36."),
        ("0.36", "Poisson's ratio .36"),
        ("1.24", "Density 1,24 g/cm3"),
        ("1240", "Density 1.24e3 kg/m3"),
        ("1240", "Density 1.24E+03 kg/m3"),
        ("8960", "Density 8,960 kg/m3"),
        ("8960", "Density 8.960 kg/m3"),
        ("8960", "Density 8 960 kg/m3"),
        ("1234.5", "1.234,5 MPa"),
        ("3.5", "Tensile modulus | 3.50 | GPa"),
    ],
)
def test_a_number_is_written_in_the_quote_in_the_pages_own_format(value: str, quote: str) -> None:
    assert written_in(Decimal(value), quote)


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("0.35", "Poisson's ratio 0.36"),
        ("0.3", "Poisson's ratio 0.35"),
        ("960", "Density 8960 kg/m3"),
        ("960", "Density 8,960 kg/m3"),
        ("1240", "Density 1.24 g/cm3"),
        ("35", "Tensile modulus 3.5 GPa"),
    ],
)
def test_a_number_the_quote_does_not_write_is_not_in_it(value: str, quote: str) -> None:
    assert not written_in(Decimal(value), quote)
