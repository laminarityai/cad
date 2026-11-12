import math

import pint
import pytest

from cad.agent_checks import formula
from cad.agent_checks.formula import Formula, dimension_of
from cad.tables.materials import UNITS


def parsed(text: str) -> Formula:
    found = formula.parse(text)
    assert isinstance(found, Formula), found
    return found


def quantity(value: float, unit: str) -> pint.Quantity:
    return UNITS.Quantity(value, unit)


def mm(value: float) -> pint.Quantity:
    return quantity(value, "mm")


def magnitude(found: pint.Quantity | str, unit: str) -> float:
    assert not isinstance(found, str), found
    return float(found.m_as(unit))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def test_a_formula_reads_its_names_and_not_its_constants() -> None:
    assert parsed("k * h * y / l**2 + 0 * pi").names == {"k", "h", "y", "l"}


@pytest.mark.parametrize(
    "text",
    [
        '__import__("os").system("true")',
        "part.volume",
        "h[0]",
        "[h]",
        "h if l else y",
        "lambda: 1",
        "h < l",
        "h and l",
        "True",
        "'2'",
        "h // l",
        "h % l",
        "open(h)",
        "sqrt(h, l)",
        "sqrt(x=h)",
        "min(h)",
        "sqrt",
        "h ** l",
        "h ** 11",
        "h ** (1 + 1)",
        "h ** 10 ** 10",
        "h +",
        "",
        "h\nl",
    ],
)
def test_anything_outside_the_grammar_is_refused_with_a_reason(text: str) -> None:
    refused = formula.parse(text)
    assert isinstance(refused, str)
    assert refused


def test_a_formula_with_more_than_its_size_of_parts_is_refused() -> None:
    assert formula.parse(" + ".join(["h"] * 100)) == "the formula has more than 120 parts"


def test_a_formula_is_evaluated_with_its_units() -> None:
    strain = formula.evaluate(
        parsed("k * h * y / l**2"),
        {"k": quantity(1.5, "dimensionless"), "h": mm(2), "y": mm(1), "l": mm(20)},
    )
    assert magnitude(strain, "percent") == pytest.approx(0.75)


def test_min_and_max_compare_across_units_and_sqrt_takes_a_root() -> None:
    values = {"a": quantity(1, "cm"), "b": mm(5)}
    assert magnitude(formula.evaluate(parsed("max(a, b)"), values), "mm") == pytest.approx(10)
    root = formula.evaluate(parsed("sqrt(a * b)"), values)
    assert magnitude(root, "mm") == pytest.approx(math.sqrt(50))


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("a / (a - a)", "the formula divides by zero"),
        ("sqrt(a - 2 * a)", "the formula takes a root of a negative number"),
        ("((a ** 10) ** 10) ** 10", "the formula's value is too large"),
        ("a * 1e308 * 1e308", "is not a finite number"),
    ],
)
def test_a_value_the_formula_cannot_take_is_a_reason_not_a_number(text: str, reason: str) -> None:
    found = formula.evaluate(parsed(text), {"a": mm(1e9)})
    assert isinstance(found, str)
    assert reason in found


def test_the_dimension_of_a_formula_comes_from_its_inputs() -> None:
    length = dimension_of("mm")
    found = formula.dimension(
        parsed("k * h * y / l**2"), {"k": dimension_of("1"), "h": length, "y": length, "l": length}
    )
    assert found == dimension_of("percent")


@pytest.mark.parametrize("text", ["h + l * l", "min(h, l * l)", "abs(h) - l ** 2"])
def test_a_sum_or_extreme_of_two_dimensions_is_refused(text: str) -> None:
    length = dimension_of("mm")
    found = formula.dimension(parsed(text), {"h": length, "l": length})
    assert isinstance(found, str)
    assert "joins values of different kinds" in found
