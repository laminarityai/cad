import pytest

from cad.sources.quantities import Quantity, Reason, Refusal, one_quantity


def kg_per_m3(quote: str) -> float:
    result = one_quantity(quote, "density")
    assert isinstance(result, Quantity), result
    return result.canonical


def refusal(quote: str) -> Refusal:
    result = one_quantity(quote, "density")
    assert isinstance(result, Refusal), result
    return result


REFUSED_OUTSIDE_THE_GRAMMAR = [
    "Density 1.24 g/cm3, filled 1.36 g/cm3 \u00b1 0.02 g/cm3",
    "Density 1.36 g/cm3 \u00b1 0.02 g/cm3 (unfilled) 1.24",
    "Density 1.24 g/cm3; GF30 1.36 \u00b1 0.02 g/cm3",
    "Density 1.24 g/cm\u00b3 \u00b1 0.02 g/cm\u00b3 (unfilled), 1.36 g/cm3",
    "Density 7850 kg/m3 \u00b1 10 kg/m3 or 7.9 g/cm3",
    "Density 1 \u00b1 0.1 240 kg/m3",
    "Density 1.24 g/cm3 \u00b1 20 kg/m3",
    "Density (max): 1.30 g/cm3",
    "Density max.: 1.30 g/cm3",
    "Density max = 1.30 g/cm3",
    "Density \u2265 1.30 g/cm3",
    "Density \u2a7e 1.30 g/cm3",
    "Density \u2267 1.30 g/cm3",
    "Density \u2a7d 1.30 g/cm3",
    "Density < = 1.30 g/cm3",
    "Density >= 1.30 g/cm3",
    "Density <= 1.30 g/cm3",
    "Density &lt; 1.30 g/cm3",
    "Density &gt; 1.30 g/cm3",
    "Density up to 1.30 g/cm3",
    "Density less than 1.30 g/cm3",
    "Density more than 1.30 g/cm3",
    "Density 1.30 g/cm3 or less",
    "Density 1.20 g/cm3 or more",
    "Density min/max 1.20/1.30 g/cm3",
    "Density max - 1.30 g/cm3",
    "Density - max 1.30 g/cm3",
    "Density 1.30 g/cm3, max",
    "Density 1.30 g/cm3 (maximum)",
    "Density 1.30 g/cm3 max.",
    "Density 1.30 g/cm3 ; max",
    "Density min. 1.20 g/cm3",
    "Density 1.20 g/cm3 minimum",
    "Density < 1.30 [g/cm3]",
    "Density [g/cm3] < 1.30",
    "Density [g/cm3] max 1.30",
    "Part 3 400 kg/m3",
    "Density 1.24 g/cm3 1.24",
    "Density 1.240 kg/m3 1.24",
    "Density 1 240 kg/m3 240",
    "Density 1.24 g/cm3 (7.85 grams per cubic centimeter)",
    "Density 7.85 grams per cubic centimeter",
    "Density 1.24 g/cm3 (0.0448 pounds per cubic inch)",
    "Density 1.24 cm3/g",
    "Density 1.24 g/cm3/K",
    "Density 1.24 g/cm3 EN 1.36 g/cm3",
    "Density ISO 1240 kg/m3",
    "Density EN 1.24 g/cm3",
    "Density 8 t m - 3 samples",
    "Density 8 t m-3 samples",
    "Density 1.24 g/cm3 1.24 g/cm3",
    "Density \u03c1 1.19 1.19 1.19 g/cm\u00b3 ISO 1183",
    "Density 1.21 g/cm3 1.21 g/cm3 ASTM D792",
    "Density \u22481.24 g/cm3",
    "Density ~1.24 g/cm3",
    "Density 1.14 g/cm3, filled ~1.36 g/cm3",
    "Density approx. 1.24 g/cm3",
    "Density 1.24 g/cm3 (23 \u00b0C)",
    "Density 1.24 g/cm3 at room temperature",
    "Density of the part",
    "see the datasheet",
    "Density 1.24 g/cm3 and specific gravity 1.3",
    "Density 1.24 g/cm3 (\u00b12%)",
    "PA6 GF30 1.36 g/cm3",
    "Density 1.24 g/cm3 30% glass",
]


@pytest.mark.parametrize("quote", REFUSED_OUTSIDE_THE_GRAMMAR)
def test_refuses_every_quote_with_text_the_grammar_does_not_account_for(quote: str) -> None:
    assert isinstance(one_quantity(quote, "density"), Refusal), quote


def test_names_the_first_token_the_grammar_cannot_account_for() -> None:
    result = refusal("Density 1.24 g/cm3 and 1.36")
    assert result.reason is Reason.UNRECOGNISED_TEXT
    assert "'and'" in result.detail


@pytest.mark.parametrize(
    "quote",
    [
        "Part 3 400 kg/m3",
        "Density 1.24 g/cm3 1.24",
        "Density 1.24 g/cm3 \u22481.36",
    ],
)
def test_a_second_number_or_stray_word_is_unrecognised_text(quote: str) -> None:
    assert refusal(quote).reason is Reason.UNRECOGNISED_TEXT


@pytest.mark.parametrize(
    "quote",
    [
        "Density 1.24 g/cm3, filled 1.36 g/cm3 \u00b1 0.02 g/cm3",
        "Density 1.24 g/cm\u00b3 \u00b1 0.02 g/cm\u00b3 (unfilled), 1.36 g/cm3",
        "Density 7850 kg/m3 \u00b1 10 kg/m3 or 7.9 g/cm3",
        "Density 1.24 g/cm3 1.24 g/cm3",
    ],
)
def test_two_values_with_units_are_several_quantities(quote: str) -> None:
    assert refusal(quote).reason is Reason.SEVERAL_QUANTITIES


@pytest.mark.parametrize(
    "quote",
    [
        "Density (max): 1.30 g/cm3",
        "Density >= 1.30 g/cm3",
        "Density &lt; 1.30 g/cm3",
        "Density up to 1.30 g/cm3",
        "Density less than 1.30 g/cm3",
        "Density 1.30 g/cm3 or less",
        "Density \u2a7d 1.30 g/cm3",
        "Density min/max 1.20/1.30 g/cm3",
    ],
)
def test_every_bound_spelling_is_a_bound(quote: str) -> None:
    assert refusal(quote).reason is Reason.BOUND


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density 1.24 g/cm3 \u00b1 0.02", 1240.0),
        ("Density 1.24 \u00b1 0.02 g/cm3", 1240.0),
        ("Density 1.24 g/cm3 \u00b1 0.02 g/cm3", 1240.0),
        ("Density 1240 kg/m3 \u00b1 20 kg/m3", 1240.0),
        ("Typical density 1.24 g/cm3", 1240.0),
        ("Nominal Density: 1.24 g/cm3", 1240.0),
        ("Dichte 1,24 g/cm3", 1240.0),
        ("Densit\u00e9 1.24 g/cm3", 1240.0),
        ("Mass density = 1.24 g/cm3", 1240.0),
        ("DIN EN ISO 1183-1 Density 1.24 g/cm3", 1240.0),
        ("Density ISO 1183:2019 1.24 g/cm3", 1240.0),
        ("Density ASTM D792 1.24 g/cm3 at 23 \u00b0C, 50 % RH", 1240.0),
        ("Density 1.24 g/cm3 @ 23\u00b0C", 1240.0),
        ("Density 1.24 g/cm3 at 1 bar", 1240.0),
    ],
)
def test_reads_what_the_grammar_allows(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize(
    "quote",
    [
        "Density 1240\u00b9 kg/m3",
        "Density\u00b9 950.0 kg/m3",
        "Density\u00b9 950 kg/m3",
        "Density\u00b9 450 kg/m3",
        "Density 1.24\u00b9 g/cm3",
        "Density 1180\u00b2 kg/m3",
        "Density 950,5\u00b3 kg/m3",
        "Density 1240\u2081 kg/m3",
        "Density \u2460 950 kg/m3",
        "Density \u00bd g/cm3",
        "Density \uff11\uff12\uff14\uff10 kg/m3",
        "Density 7.\u09ea5 g/cm3",
        "Density \u09ed.\u09ee\u09eb g/cm3",
        "Density \u0967\u0968\u096a\u0966 kg/m3",
    ],
)
def test_refuses_a_superscript_subscript_or_non_ascii_digit(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.UNRECOGNISED_TEXT
    assert "digit" in result.detail


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Density 1.24 g/cm\u00b3", 1240.0),
        ("Density 1240 kg/m\u00b3", 1240.0),
        ("Density 0.0448 lb/in\u00b3", 1240.0),
        ("Density 1.24 g\u00b7cm\u207b\u00b3", 1240.0),
        ("Density 1240 kg\u00b7m\u207b\u00b3", 1240.0),
        ("Density 1.24 g/\u33a4", 1240.0),
        ("Density 1240 kg/\u33a5", 1240.0),
    ],
)
def test_still_reads_a_cubed_length_unit(quote: str, expected: float) -> None:
    assert kg_per_m3(quote) == pytest.approx(expected, rel=1e-3)


@pytest.mark.parametrize(
    "quote",
    [
        "Density 1 950.0 kg/m3",
        "Density ISO 1183 1 950.0 kg/m3",
        "Density DIN 53479 1 950.0 kg/m3",
        "Density 7 850,5 kg/m3",
        "Density DIN 7 850 kg/m3",
        "Density DIN 1 950.0 kg/m3",
    ],
)
def test_a_space_grouped_number_with_a_decimal_is_ambiguous_or_refused(quote: str) -> None:
    assert isinstance(one_quantity(quote, "density"), Refusal)
    assert "950" not in str(kg_per_m3_or_none(quote))


def kg_per_m3_or_none(quote: str) -> float | None:
    result = one_quantity(quote, "density")
    return result.canonical if isinstance(result, Quantity) else None


def test_a_space_grouped_decimal_is_ambiguous_even_when_one_reading_is_out_of_band() -> None:
    assert refusal("Density 1 950.0 kg/m3").reason is Reason.AMBIGUOUS_NUMBER
    assert refusal("Density 1 240.0 kg/m3").reason is Reason.AMBIGUOUS_NUMBER


@pytest.mark.parametrize(
    "quote", ["Density 1.24 g/\u0131n3", "Density 1.24 lb/\u0131n3", "Density 1.24 K\u212a/m3"]
)
def test_a_unicode_lookalike_of_a_unit_letter_is_refused_not_raised(quote: str) -> None:
    assert isinstance(one_quantity(quote, "density"), Refusal)


def test_the_reader_never_raises_on_random_unicode() -> None:
    import random

    seeds = [
        "Density 1.24 g/cm3",
        "Density [g/cm3] 1.24 ISO 1183",
        "Density 1 240,5 kg/m3 \u00b1 2%",
        "Density at 23 \u00b0C 0.0448 lbs./in.3",
        "1.20-1.25 g/cm\u00b3",
    ]
    alphabet = [chr(c) for c in range(0x20, 0x250)] + [chr(c) for c in range(0x0900, 0x0980)]
    alphabet += [chr(c) for c in range(0x2000, 0x2200)] + [chr(c) for c in range(0xFF00, 0xFFF0)]
    rng = random.Random(66)
    for _ in range(4000):
        chars = list(rng.choice(seeds))
        for _ in range(rng.randint(1, 4)):
            chars.insert(rng.randint(0, len(chars)), rng.choice(alphabet))
        result = one_quantity("".join(chars), "density")
        assert isinstance(result, Quantity | Refusal)
    for _ in range(2000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 80)))
        assert isinstance(one_quantity(text, "density"), Quantity | Refusal)


def test_a_header_dump_is_not_called_a_range() -> None:
    result = refusal(
        "Density [lb/in\u00b3] [g/cm\u00b3] Coef. [10-6/\u00b0F] [10-6/K] 1981 0.323 8.9"
    )
    assert result.reason is Reason.MISSING_UNIT
    assert "choose the figure" not in result.needed


def test_the_aurubis_quote_reports_a_missing_unit() -> None:
    from cad.tables.materials import Cited, load_materials

    density = load_materials().materials["aurubis-c11000-h02"].density
    assert isinstance(density, Cited)
    result = refusal(density.source.quote)
    assert result.reason is Reason.MISSING_UNIT
    assert "choose the figure" not in result.needed


def test_a_malformed_exponent_is_an_unknown_unit_not_a_range() -> None:
    result = refusal("Density 1.24 g/cm\u207b\u00b3 x")
    assert result.reason is not Reason.RANGE
    assert refusal("Density 1.24 g/cm-3").reason is Reason.UNKNOWN_UNIT


def test_a_stray_condition_next_to_a_value_is_unrecognised_text() -> None:
    result = refusal("Density 1.24 g/cm3 23C")
    assert result.reason is Reason.UNRECOGNISED_TEXT
    assert "23" in result.detail
