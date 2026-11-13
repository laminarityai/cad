import pytest
from cases import BY_NAME

from cad.checks.container.fea import ERROR_BOUNDS


@pytest.mark.parametrize("name", list(BY_NAME))
def test_each_hand_calculation_holds_within_the_bound_the_check_states(name: str) -> None:
    case = BY_NAME[name]
    assert case.tolerance <= ERROR_BOUNDS[case.measure]
