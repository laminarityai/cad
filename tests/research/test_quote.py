from decimal import Decimal

import pytest

from cad.research.quote import on_page, written_in


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("Density 8960 kg/m3", "Density 8960 kg/m3"),
        ("Poisson's ratio 0.35", "(Poisson's ratio 0.35)"),
        ("Poisson's ratio 0.35", "Poisson's ratio 0.35. Density 1.24 g/cm3"),
        ("Poisson's ratio 0.35", "Poisson's ratio 0.3 and Poisson's ratio 0.35"),
        ("DENSITY 1.21 G/CM3", "Density\u00a01.21 g/cm\u00b3"),
        ("Poisson\u2019s ratio 0.35", "Poisson's   ratio\n0.35"),
        ("Density 1250 kg/m3", "Density 1250 kg/m 3 Mechanical properties"),
        ("Density | 1.25 g/cm3 at 23\u00b0C", "Density 1.25 g/cm3 at 23 \u00b0C"),
        ("Density (\u03c1): 2.70 g/cm3", "Density ( \u03c1 ) 2.70 g/cm 3 [ 1 ]"),
        ("1.24 g/cm3", "Density 1.20-1.24 g/cm3"),
        ("of at least 240 MPa (35 ksi).", "of at least 240 MPa (35 ksi) [3] ."),
        ("Tensile strength 55-75 MPa", "Tensile strength 55\u201375 MPa"),
        ("TensileStrength: 50 MPa", "Tensile strength 50 MPa"),
    ],
)
def test_spacing_punctuation_markup_and_case_may_differ(quote: str, text: str) -> None:
    assert on_page(quote, text)


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("960 kg/m3", "Density: 8960 kg/m3"),
        ("960 kg/m3", "Density 8,960 kg/m3"),
        ("1.34 g/cm3", "Density 11.34 g/cm3"),
        ("Poisson's ratio 0.3", "Poisson's ratio 0.35"),
        ("34 g/cm3", "Density .34 g/cm3"),
        ("Young's modulus 2.1", "Young's modulus 2.1e5 MPa"),
        ("Density 124 kg/m3", "Density 1.24 kg/m3"),
        ("Density 1 24", "Density 124"),
        ("Poisson's ratio 0.38", "Poisson's ratio \u03bd 0.38"),
    ],
)
def test_a_quote_whose_words_or_numbers_differ_is_not_on_the_page(quote: str, text: str) -> None:
    assert not on_page(quote, text)


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("0.36", "the Poisson ratio = 0.36, was used"),
        ("0.36", "Poisson's ratio .36"),
        ("1.24", "Density 1,24 g/cm3"),
        ("1240", "Density 1.24e3 kg/m3"),
        ("1240", "Density 1.24E+03 kg/m3"),
        ("8960", "Density 8,960 kg/m3"),
        ("8960", "Density 8 960 kg/m3"),
        ("1234.5", "1.234,5 MPa"),
        ("3.5", "Tensile modulus | 3.50 | GPa"),
        ("75", "55-75 MPa"),
    ],
)
def test_a_number_is_written_in_the_quote_in_the_pages_own_format(value: str, quote: str) -> None:
    assert written_in(Decimal(value), quote)


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("0.35", "Poisson's ratio 0.36"),
        ("1.2", "Density 1.24 g/cm3"),
        ("124", "Density 1.24 g/cm3"),
        ("1.24", "Density 124 kg/m3"),
        ("960", "Density 8960 kg/m3"),
        ("35", "Tensile modulus 3.5 GPa"),
        ("2.1", "Young's modulus 2.1e5 MPa"),
        ("638", "Tested to ASTM D638-14, tensile strength 50 MPa"),
        ("3", "Density 1.25 g/cm3"),
    ],
)
def test_digits_that_are_not_the_whole_number_are_not_the_value(value: str, quote: str) -> None:
    assert not written_in(Decimal(value), quote)


def test_a_comma_number_reads_both_ways() -> None:
    assert written_in(Decimal("1.337"), "1,337")
    assert written_in(Decimal("1337"), "1,337")
