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
        ("24 g/cm3", "Density 1.20-1.24 g/cm3"),
        ("Poisson's ratio 0.38", "Poisson's ratio \u03bd 0.38"),
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
        ("Density 1250 kg/m3", "Density 1250 kg/m 3 Mechanical properties"),
        ("Density | 1.25 g/cm3 at 23\u00b0C", "Density 1.25 g/cm3 at 23 \u00b0C"),
        ("Density (\u03c1): 2.70 g/cm3", "Density ( \u03c1 ) 2.70 g/cm 3 [ 1 ]"),
        ("1.24 g/cm3", "Density 1.20-1.24 g/cm3"),
        ("of at least 240 MPa (35 ksi).", "of at least 240 MPa (35 ksi) [3] ."),
        ("Table 3. It can be seen", "given in Table 3 . It can be seen"),
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


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("638", "Tested to ASTM D638-14, tensile strength 50 MPa"),
        ("3", "Density 1.25 g/cm3"),
        ("6", "Alloy 6061-T6, yield strength 276 MPa"),
        ("0.3", "Poisson's ratio -0.3"),
        ("0.3", "Poisson's ratio \u22120.3"),
        ("2.1", "Young's modulus 2.1e5 MPa"),
    ],
)
def test_digits_inside_a_longer_token_or_a_signed_number_are_not_the_value(
    value: str, quote: str
) -> None:
    assert not written_in(Decimal(value), quote)


@pytest.mark.parametrize(
    ("value", "quote"),
    [("-0.3", "Poisson's ratio \u22120.3"), ("14", "ASTM D638-14"), ("75", "55-75 MPa")],
)
def test_a_sign_is_read_and_a_range_dash_is_not(value: str, quote: str) -> None:
    assert written_in(Decimal(value), quote)


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("Young's modulus 2.1", "Young's modulus 2.1e5 MPa"),
        ("Young's modulus 2.1", "Young's modulus 2.1E-5 MPa"),
        ("5 MPa", "Young's modulus 2.1e5 MPa"),
        ("5 MPa", "Young's modulus 2.1e-5 MPa"),
        ("Poisson's ratio 0.3", "Poisson's ratio -0.3"),
        ("0.3", "Poisson's ratio \u22120.3"),
        ("638-14", "Tested to ASTM D638-14"),
        ("Pa) 200000", "Tensile strength (kPa) 200000"),
        ("Tensile strength (M", "Tensile strength (MPa) 55"),
    ],
)
def test_a_quote_that_drops_a_sign_or_exponent_or_cuts_a_word_is_not_on_the_page(
    quote: str, text: str
) -> None:
    assert not on_page(quote, text)


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("Poisson's ratio -0.3", "Poisson's ratio \u22120.3"),
        ("Tensile strength 55-75 MPa", "Tensile strength 55\u201375 MPa"),
        ("Young's modulus 2.1e5 MPa", "Young's modulus 2.1e5 MPa"),
        ("1.41g/cm\u00b3", "Density 1.41g/cm\u00b3 at 23 \u00b0C"),
    ],
)
def test_a_signed_ranged_or_unit_glued_number_quoted_whole_is_on_the_page(
    quote: str, text: str
) -> None:
    assert on_page(quote, text)
