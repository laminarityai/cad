import pytest
from mcp import Client

from cad.operations.guidance import COLOURS
from cad.sandbox.outcome import AreaCount, BuiltTold
from cad.server.app import build_server


def test_the_agent_is_told_to_read_the_areas_it_kept_not_only_areas_dropped() -> None:
    named = (set(BuiltTold.model_fields) | set(AreaCount.model_fields)) - {"kind", "name"}
    assert {field for field in named if field not in COLOURS} == set()
    assert "says why a colour was not kept" not in COLOURS


@pytest.mark.anyio
async def test_every_client_is_told_to_colour_a_one_material_build_before_it_builds() -> None:
    async with Client(build_server()) as client:
        instructions = client.instructions or ""
    assert "Colour every build" in instructions
    assert "a part of one material included" in instructions
    assert "set color on result, or on each body when there are several" in instructions
    assert "result.color" not in instructions
    assert "never in a build of its own" not in instructions


@pytest.mark.anyio
async def test_every_client_is_asked_for_areas_in_a_sentence_of_their_own() -> None:
    async with Client(build_server()) as client:
        instructions = client.instructions or ""
    sentence = next(one for one in instructions.split(". ") if "a person would point" in one)
    assert sentence.startswith("Then give each area")
    assert "areas = [Compound(result.faces()" in sentence


@pytest.mark.anyio
async def test_a_colour_change_alone_is_the_slots_next_revision() -> None:
    async with Client(build_server()) as client:
        instructions = client.instructions or ""
    assert "asks only for other colours gets the slot's next revision" in instructions
