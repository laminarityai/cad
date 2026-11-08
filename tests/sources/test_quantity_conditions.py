import pytest

from cad.sources.quantities import Reason, Refusal, one_quantity


def refusal(quote: str) -> Refusal:
    result = one_quantity(quote, "density")
    assert isinstance(result, Refusal), result
    return result


@pytest.mark.parametrize(
    ("quote", "reason"),
    [
        ("1.24 at 23 °C at 80 °C", Reason.MISSING_UNIT),
        ("-1.24 g/cm3 at 23 °C at 80 °C", Reason.NEGATIVE),
        ("1240. kg/m3 at 23 °C at 80 °C", Reason.TRAILING_DECIMAL),
        (",9 g/cm3 at 23 °C at 80 °C", Reason.AMBIGUOUS_NUMBER),
        ("1.24 g/cm 3 at 23 °C at 80 °C", Reason.UNKNOWN_UNIT),
        ("1.24 g/cm3 at 23 °C at 80 °C foo", Reason.UNRECOGNISED_TEXT),
        ("ISO 1183 2019 kg/m3 at 23 °C at 80 °C", Reason.AMBIGUOUS_NUMBER),
    ],
)
def test_two_conditions_do_not_hide_a_more_specific_reason(quote: str, reason: Reason) -> None:
    assert refusal(quote).reason is reason


@pytest.mark.parametrize(
    "quote",
    [
        "1.24 g/cm3 at 23 °C at 296 K",
        "1.24 g/cm3 at 23 °C at 296.15 K",
        "1.24 g/cm3 at 23 °C at 73.4 °F",
        "at 23 °C 1.24 g/cm3 at 23.0 °C",
        "Density at 23°C 1.24 g/cm3 at 73 °F",
        "Density at 1 bar 1.24 g/cm3 at 100 kPa",
    ],
)
def test_one_condition_stated_twice_in_two_spellings_says_so(quote: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.SEVERAL_CONDITIONS
    assert "twice" in result.detail
    assert "different" not in result.detail


@pytest.mark.parametrize(
    ("quote", "kind"),
    [
        ("1.24 g/cm3 at 23 °C at 80 °C", "temperatures"),
        ("1.24 g/cm3 at 23 °C at -40 °C", "temperatures"),
        ("1.24 g/cm3 at 23 °C at 300 K", "temperatures"),
        ("1.24 g/cm3 at 23 °C at 75 °F", "temperatures"),
        ("1.2 kg/m3 at 1 bar at 10 bar", "pressures"),
    ],
)
def test_two_different_conditions_say_they_differ(quote: str, kind: str) -> None:
    result = refusal(quote)
    assert result.reason is Reason.SEVERAL_CONDITIONS
    assert f"two different {kind}" in result.detail
