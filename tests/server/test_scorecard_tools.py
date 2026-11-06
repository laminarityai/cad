import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from cad.scorecard import score
from cad.server.app import build_server
from cad.tables.materials import load_materials

pytestmark = pytest.mark.anyio

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
UNBUILT_ID = "0123456789abcdef"


def text_of(result: Any) -> str:
    return json.dumps([block.model_dump() for block in result.content])


def numbers_in(value: object) -> list[str]:
    found: list[str] = []

    def keep(text: str) -> str:
        found.append(text)
        return text

    json.loads(json.dumps(value), parse_int=keep, parse_float=keep)
    return found


async def test_list_materials_returns_every_key_and_name_and_no_number() -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("list_materials", {})
    assert not result.is_error
    table = load_materials()
    assert result.structured_content == {
        "materials": [{"key": m.key, "name": m.name} for m in table.materials.values()]
    }
    assert len(table.materials) == 5
    assert numbers_in(result.structured_content) == []


async def test_score_variant_with_an_unknown_variant_id_is_an_error_naming_the_id(
    tmp_path: Path,
) -> None:
    async with Client(build_server(tmp_path)) as client:
        result = await client.call_tool(
            "score_variant", {"variant_id": UNBUILT_ID, "material_key": "prusament-pla"}
        )
    assert result.is_error
    assert UNBUILT_ID in text_of(result)


async def test_score_variant_with_a_malformed_id_is_an_error_naming_the_id(tmp_path: Path) -> None:
    async with Client(build_server(tmp_path)) as client:
        result = await client.call_tool(
            "score_variant", {"variant_id": "../../etc", "material_key": "prusament-pla"}
        )
    assert result.is_error
    assert "../../etc" in text_of(result)


async def test_build_then_score_returns_the_scorecard_it_stored(tmp_path: Path) -> None:
    async with Client(build_server(tmp_path)) as client:
        built = await client.call_tool("build_variant", {"code": PLATE})
        assert built.structured_content is not None
        variant_id = built.structured_content["variant_id"]
        scored = await client.call_tool(
            "score_variant", {"variant_id": variant_id, "material_key": "prusament-pla"}
        )
    assert not scored.is_error, text_of(scored)
    assert scored.structured_content is not None
    verdicts = {r["check_id"]: r["verdict"] for r in scored.structured_content["results"]}
    assert verdicts == {"closed_solid": "pass", "interference": "pass", "mass": "pass"}
    stored = json.loads((tmp_path / variant_id / score.SCORECARD).read_text())
    assert stored == scored.structured_content


async def test_score_variant_rejects_an_argument_it_does_not_declare(tmp_path: Path) -> None:
    async with Client(build_server(tmp_path)) as client:
        result = await client.call_tool(
            "score_variant",
            {"variant_id": UNBUILT_ID, "material_key": "prusament-pla", "verdict": "pass"},
        )
    assert result.is_error
    assert "verdict" in text_of(result)
