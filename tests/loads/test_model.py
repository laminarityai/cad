import pytest
from pydantic import TypeAdapter, ValidationError

from cad.loads.model import LoadCase

HOOK = {
    "support": {"kind": "holes", "count": 2, "diameter": {"magnitude": 5.5, "unit": "mm"}},
    "load": {
        "kind": "far_end",
        "force": {"magnitude": 49.0, "unit": "N"},
        "direction": {"kind": "across", "axis": "hole_axis"},
    },
}
CASE = TypeAdapter(LoadCase)


def hook(**load: object) -> LoadCase:
    return CASE.validate_python({**HOOK, "load": {**HOOK["load"], **load}})


def test_a_load_case_crosses_the_wire_in_millimetres_and_newtons() -> None:
    assert hook(force={"magnitude": 0.049, "unit": "kN"}).wire() == {
        "support": {"kind": "holes", "count": 2, "diameter_mm": 5.5},
        "load": {
            "kind": "far_end",
            "force_n": 49.0,
            "direction": {"kind": "across", "axis": "hole_axis"},
        },
    }


def test_the_same_case_in_other_units_has_the_same_id() -> None:
    assert hook(force={"magnitude": 0.049, "unit": "kN"}).id == hook().id
    assert len(hook().id) == 8


def test_cases_that_differ_only_in_force_share_unit_solves_but_not_an_id() -> None:
    heavier = hook(force={"magnitude": 98.0, "unit": "N"})
    assert heavier.id != hook().id
    assert heavier.unit_case == hook().unit_case
    assert hook(direction={"kind": "any"}).unit_case != hook().unit_case


@pytest.mark.parametrize(
    "load",
    [
        {"force": {"magnitude": -1, "unit": "N"}},
        {"force": {"magnitude": 5, "unit": "kg"}},
        {"direction": {"kind": "along", "axis": "sideways"}},
        {"kind": "on_holes", "count": 13},
    ],
)
def test_a_load_outside_the_vocabulary_is_refused(load: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        hook(**load)
