import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from cad.server.app import build_server

pytestmark = pytest.mark.anyio

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
KEY = {"material_key": "prusament-pla"}


def text_of(result: Any) -> str:
    return json.dumps([block.model_dump() for block in result.content])


async def test_scorecard_returns_the_card_score_variant_made_and_runs_no_check(
    tmp_path: Path,
) -> None:
    async with Client(build_server(tmp_path)) as client:
        built = await client.call_tool("build_variant", {"code": PLATE})
        assert built.structured_content is not None
        variant_id = built.structured_content["variant_id"]
        scored = await client.call_tool("score_variant", {"variant_id": variant_id, **KEY})
        jobs = sorted((tmp_path / variant_id / "jobs").iterdir())
        read = await client.call_tool("scorecard", {"variant_id": variant_id, **KEY})
    assert not scored.is_error, text_of(scored)
    assert not read.is_error, text_of(read)
    assert read.structured_content == scored.structured_content
    assert sorted((tmp_path / variant_id / "jobs").iterdir()) == jobs


async def test_scorecard_of_a_variant_never_scored_is_refused_and_starts_nothing(
    tmp_path: Path,
) -> None:
    async with Client(build_server(tmp_path)) as client:
        built = await client.call_tool("build_variant", {"code": PLATE})
        assert built.structured_content is not None
        variant_id = built.structured_content["variant_id"]
        read = await client.call_tool("scorecard", {"variant_id": variant_id, **KEY})
    assert read.is_error
    assert "NotScored" in text_of(read)
    assert variant_id in text_of(read)
    assert not (tmp_path / variant_id / "jobs").exists()


async def test_scorecard_of_an_unknown_variant_is_refused_naming_the_id(tmp_path: Path) -> None:
    async with Client(build_server(tmp_path)) as client:
        read = await client.call_tool("scorecard", {"variant_id": "0123456789abcdef", **KEY})
    assert read.is_error
    assert "0123456789abcdef" in text_of(read)


async def test_no_scorecard_file_is_written_by_scoring(tmp_path: Path) -> None:
    async with Client(build_server(tmp_path)) as client:
        built = await client.call_tool("build_variant", {"code": PLATE})
        assert built.structured_content is not None
        variant_id = built.structured_content["variant_id"]
        await client.call_tool("score_variant", {"variant_id": variant_id, **KEY})
    assert not list(tmp_path.rglob("scorecard*"))
