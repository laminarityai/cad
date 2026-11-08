import pytest

from cad.sources.quantities import Quantity, Reason, Refusal, one_quantity
from cad.sources.standards import STANDARDS


def kg_per_m3(quote: str) -> float:
    result = one_quantity(quote, "density")
    assert isinstance(result, Quantity), result
    return result.canonical


def refusal(quote: str) -> Refusal:
    result = one_quantity(quote, "density")
    assert isinstance(result, Refusal), result
    return result


SPELLINGS = [spelling for spellings in STANDARDS.values() for spelling in spellings]


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_a_listed_standard_ends_where_its_spelling_ends(spelling: str) -> None:
    assert kg_per_m3(f"Density {spelling} 1.24 g/cm3") == pytest.approx(1240.0)
    assert kg_per_m3(f"Density {spelling}: 1.24 g/cm3") == pytest.approx(1240.0)


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density ISO 1183 1.24 g/cm³", 1240.0),
        ("Density ISO1183, GB/T1033 1.04 g/cm3 at 23°C", 1040.0),
        ("Density ISO 1183 1240.5 kg/m3", 1240.5),
        ("Density ASTM D792-13 1.24 g/cm3", 1240.0),
        ("Density ASTM D1505 0.95 g/cm3", 950.0),
        ("Density GB/T 1033.1 1.24 g/cm3", 1240.0),
        ("Density DIN EN ISO 1183-1 1.24 g/cm3", 1240.0),
        ("Density DIN EN ISO 1183-1 0,95 g/cm3", 950.0),
        ("Density DIN 53479 1.24 g/cm3", 1240.0),
        ("Density JIS K 7112 1.24 g/cm3", 1240.0),
        ("Density ISO 1183-1:2019 1.24 g/cm3", 1240.0),
        ("Density ISO 1183-3 1.24 g/cm3", 1240.0),
        ("Density ISO 1183-1 1,24 g/cm3", 1240.0),
        ("Density \uff29\uff33\uff2f 1183 1.24 g/cm3", 1240.0),
        ("Density EN ISO 1183-1:2019 1.24 g/cm3", 1240.0),
        ("Density JIS K 7112:1999 1.24 g/cm3", 1240.0),
        ("Density JIS K 7112-1 1.24 g/cm3", 1240.0),
        ("Density JIS K 7112-1:2023 1.24 g/cm3", 1240.0),
        ("Density DIN EN ISO 1183-2:2019 1.24 g/cm3", 1240.0),
        ("Density ISO 1183:2019 1.24 g/cm3", 1240.0),
    ],
)
def test_a_number_after_a_listed_standard_reads(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected)


def test_a_large_value_after_a_listed_standard_is_a_value_question_not_a_parse_question() -> None:
    assert kg_per_m3("Density ISO 1183 12.4 g/cm3") == pytest.approx(12400.0)
    assert refusal("Density ISO 1183 124.0 g/cm3").reason is Reason.OUT_OF_BAND


def test_the_longest_listed_spelling_wins() -> None:
    assert kg_per_m3("Density ISO 1183-1 1.24 g/cm3") == pytest.approx(1240.0)
    assert refusal("Density ISO 1183-1 0.24 g/cm3").reason is Reason.OUT_OF_BAND


@pytest.mark.parametrize(
    "quote",
    [
        "Density ISO 11831.24 g/cm3",
        "Density ISO 1183-1240 kg/m3",
        "Density ISO 1183-11.24 g/cm3",
        "Density GB/T 1033.11.24 g/cm3",
        "Density ASTM D7921.24 g/cm3",
        "Density ISO 1183:1 1.24 g/cm3",
    ],
)
def test_a_listed_standard_glued_to_more_digits_is_refused(quote: str) -> None:
    assert refusal(quote).reason is Reason.AMBIGUOUS_NUMBER


@pytest.mark.parametrize(
    ("quote", "standard"),
    [
        ("Density DIN 1 2400.5 kg/m3", "DIN 1"),
        ("Density DIN 1 2400,5 kg/m3", "DIN 1"),
        ("Density ASTM D7 9200.0 kg/m3", "ASTM D7"),
        ("Density DIN 1 12.4 g/cm3", "DIN 1"),
        ("Density GB/T 1033-2010 1.24 g/cm3", "GB/T 1033-2010"),
        ("Density ISO 1183-4 1.24 g/cm3", "ISO 1183-4"),
        ("Density ISO 118 31.24 g/cm3", "ISO 118"),
    ],
)
def test_an_unlisted_standard_followed_by_a_number_is_refused_by_name(
    quote: str, standard: str
) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert repr(standard) in result.detail
    assert "list of density test standards" in result.detail
    assert "added" in result.needed


@pytest.mark.parametrize(
    "quote",
    [
        "Density ISO 1183 1 240 kg/m3",
        "Density ISO 1183-1 1 240 kg/m3",
        "Density ISO 1183:2019 1 240 kg/m3",
        "Density ISO 1183 1 2400.5 kg/m3",
        "Density ISO 1183 2019 1.24 g/cm3",
        "Density ISO 1183:1240 kg/m3",
    ],
)
def test_a_listed_standard_does_not_hide_a_split_or_extra_number(quote: str) -> None:
    assert isinstance(one_quantity(quote, "density"), Refusal)


@pytest.mark.parametrize(
    ("quote", "standard", "number"),
    [
        ("Density GB/T 1033.1 2008 kg/m3", "GB/T 1033.1", "2008"),
        ("ISO 1183 2019 kg/m3", "ISO 1183", "2019"),
        ("ASTM D792 2013 kg/m3", "ASTM D792", "2013"),
        ("Density ASTM D792-13 2013 kg/m3", "ASTM D792-13", "2013"),
        ("Density DIN EN ISO 1183-1 2019 kg/m3", "DIN EN ISO 1183-1", "2019"),
        ("ISO 1183-1: 2019 kg/m3", "ISO 1183-1", "2019"),
        ("Density ISO 1183-1, 2019 kg/m3", "ISO 1183-1", "2019"),
        ("Density ASTM D792 - 2013 kg/m3", "ASTM D792", "2013"),
        ("Density ISO 1183 2019 1.24 g/cm3", "ISO 1183", "2019"),
        ("Density ISO 1183 1240 kg/m3", "ISO 1183", "1240"),
        ("Density ISO 1183-1:2019 1240 kg/m3", "ISO 1183-1:2019", "1240"),
        ("Density ISO 1183 2150 kg/m3", "ISO 1183", "2150"),
    ],
)
def test_a_plain_integer_right_after_a_listed_standard_could_be_its_edition_year(
    quote: str, standard: str, number: str
) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert repr(standard) in result.detail
    assert repr(number) in result.detail
    assert "edition year" in result.detail


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density ISO 1183 1240.5 kg/m3", 1240.5),
        ("Density ISO 1183 2.15 g/cm3", 2150.0),
        ("Density ISO 1183 at 23 °C 1240 kg/m3", 1240.0),
        ("Density 1240 kg/m3 ISO 1183", 1240.0),
    ],
)
def test_a_number_that_cannot_be_an_edition_year_still_reads(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected)


@pytest.mark.parametrize("quote", ["Density ISO 1183:1240 kg/m3", "ISO 1183-1:1240 kg/m3"])
def test_digits_glued_to_a_standard_before_the_unit_are_named(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert "'1240'" in result.detail
    assert "edition year" in result.detail


@pytest.mark.parametrize(
    ("quote", "number"),
    [
        ("ASTM D4892, 2014 kg/m3", "2014"),
        ("ASTM D792-08: 2008 kg/m3", "2008"),
        ("ISO 1183:2004, 2004 kg/m3", "2004"),
        ("DIN 1, 2400 kg/m3", "2400"),
        ("ASTM D7; 9200 kg/m3", "9200"),
        ("ISO 1183; 2019 kg/m3", "2019"),
        ("ISO 1183 = 2019 kg/m3", "2019"),
        ("ISO 1183 , : 2019 kg/m3", "2019"),
        ("ISO 1183 :: 2019 kg/m3", "2019"),
        ("ISO 1183 ,, 2019 kg/m3", "2019"),
        ("ISO 1183 (2019) kg/m3", "2019"),
        ("ISO 1183 [ 2019 kg/m3", "2019"),
        ("ISO 1183 ; - 2019 kg/m3", "2019"),
        ("ASTM D792 -13 1.24 g/cm3", "13"),
        ("JIS K 7112-1:2023,5 kg/m3", "5"),
    ],
)
def test_a_whole_number_reached_from_a_standard_through_separators_is_refused(
    quote: str, number: str
) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert repr(number) in result.detail
    assert "standard" in result.detail


@pytest.mark.parametrize(
    ("quote", "standard"),
    [
        ("ASTM D4892, 2014 kg/m3", "ASTM D4892"),
        ("DIN 1, 2400 kg/m3", "DIN 1"),
        ("ASTM D7; 9200 kg/m3", "ASTM D7"),
        ("DIN 1 : 2400.5 kg/m3", "DIN 1"),
        ("ASTM D 4892 1.24 g/cm3", "ASTM D 4892"),
    ],
)
def test_an_unlisted_standard_followed_through_separators_by_a_number_is_refused_by_name(
    quote: str, standard: str
) -> None:
    result = refusal(quote)
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert repr(standard) in result.detail
    assert "list of density test standards" in result.detail


@pytest.mark.parametrize(
    "quote",
    [
        "ISO 1183 Density 2019 kg/m3",
        "ISO 1183 at 23 °C 2019 kg/m3",
        "ISO 1183 kg/m3 2019",
        "Density (ISO 1183) 2019 kg/m3",
        "Density [ISO 1183] 2019 kg/m3",
        "ISO 1183, 2019.0 kg/m3",
    ],
)
def test_a_label_condition_unit_or_closing_bracket_ends_the_standard(quote: str) -> None:
    assert kg_per_m3(quote) == pytest.approx(2019.0)


def test_a_standard_glued_to_a_decimal_number_says_where_it_is_unclear() -> None:
    result = refusal("JIS K 7112-1.24 g/cm3")
    assert result.reason is Reason.AMBIGUOUS_NUMBER
    assert "standard" in result.detail


def test_astm_d_792_with_a_space_and_an_edition_is_listed() -> None:
    assert kg_per_m3("ASTM D 792-13 1.24 g/cm3") == pytest.approx(1240.0)
