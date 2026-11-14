from cad.operations.guidance import COLOURS
from cad.sandbox.outcome import AreaCount, BuiltTold


def test_the_agent_is_told_to_read_the_areas_it_kept_not_only_areas_dropped() -> None:
    named = (set(BuiltTold.model_fields) | set(AreaCount.model_fields)) - {"kind", "name"}
    assert {field for field in named if field not in COLOURS} == set()
    assert "says why a colour was not kept" not in COLOURS
