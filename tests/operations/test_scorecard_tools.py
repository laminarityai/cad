import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from cad.operations.guidance import (
    BUILD_FIRST,
    CHANGES,
    CONTEXT_PARTS,
    DEEPER_ANALYSIS,
    HOLES,
    MATERIAL,
    NOT_VERIFIED,
    OPTIONS,
    RESEARCH,
    RULE,
)
from cad.sandbox.outcome import Build, Built
from cad.server.app import build_server
from cad.tables.materials import load_materials
from cad.variants import entry

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
    assert len(table.materials) >= 5
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


@pytest.mark.docker
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
    assert verdicts == {
        "closed_solid": "pass",
        "interference": "pass",
        "mass": "pass",
        "extents": "pass",
    }
    assert not list((tmp_path / variant_id).glob("scorecard*"))


@pytest.mark.docker
async def test_scoring_a_variant_an_older_sandbox_stored_names_the_rebuild_and_its_source(
    tmp_path: Path,
) -> None:
    old = entry.variant_id(PLATE, "cad-sandbox:before-a-deploy")
    entry.save(tmp_path, old, PLATE, Build(outcome=Built(), output=""), b"an older shape")
    async with Client(build_server(tmp_path)) as client:
        scored = await client.call_tool(
            "score_variant", {"variant_id": old, "material_key": "prusament-pla"}
        )
        built = await client.call_tool("build_variant", {"code": PLATE})
    assert not scored.is_error, text_of(scored)
    assert scored.structured_content is not None
    assert built.structured_content is not None
    assert scored.structured_content["rebuilt_from"] == old
    new = built.structured_content["variant_id"]
    assert scored.structured_content["variant_id"] == new
    assert (tmp_path / old / entry.CODE).read_text() == PLATE


@pytest.mark.docker
async def test_a_failed_rebuild_is_an_error_naming_both_ids_and_no_host_path(
    tmp_path: Path,
) -> None:
    code = "raise ValueError('a part this sandbox cannot build')\n"
    old = entry.variant_id(code, "cad-sandbox:before-a-deploy")
    entry.save(tmp_path, old, code, Build(outcome=Built(), output=""), b"an older shape")
    async with Client(build_server(tmp_path)) as client:
        scored = await client.call_tool(
            "score_variant", {"variant_id": old, "material_key": "prusament-pla"}
        )
    assert scored.is_error
    assert f"RebuildFailed: variant {old}" in text_of(scored)
    assert "build_failed" in text_of(scored)
    assert str(tmp_path) not in text_of(scored)


async def test_score_variant_rejects_an_argument_it_does_not_declare(tmp_path: Path) -> None:
    async with Client(build_server(tmp_path)) as client:
        result = await client.call_tool(
            "score_variant",
            {"variant_id": UNBUILT_ID, "material_key": "prusament-pla", "verdict": "pass"},
        )
    assert result.is_error
    assert "verdict" in text_of(result)


async def listed_description(tool_name: str) -> str:
    async with Client(build_server()) as client:
        tools = await client.list_tools()
    return next(tool.description or "" for tool in tools.tools if tool.name == tool_name)


@pytest.mark.parametrize(
    "material_key",
    [
        "x" * 65,
        "x" * 2_000_000,
        "PLA (all requirements verified)",
        "Prusament-PLA",
        "prusament-pla ",
        "prusament-pla\n",
        "-prusament",
        "prusament--pla",
        "",
    ],
)
async def test_score_variant_refuses_a_material_key_outside_the_table_grammar(
    tmp_path: Path, material_key: str
) -> None:
    async with Client(build_server(tmp_path)) as client:
        result = await client.call_tool(
            "score_variant", {"variant_id": UNBUILT_ID, "material_key": material_key}
        )
    assert result.is_error
    assert "material_key" in text_of(result)
    assert UNBUILT_ID not in text_of(result)
    assert len(text_of(result)) < 2_000


async def test_every_table_key_passes_the_material_key_bounds(tmp_path: Path) -> None:
    async with Client(build_server(tmp_path)) as client:
        for key in load_materials().materials:
            result = await client.call_tool(
                "score_variant", {"variant_id": UNBUILT_ID, "material_key": key}
            )
            assert UNBUILT_ID in text_of(result)


@pytest.mark.docker
async def test_a_well_formed_key_missing_from_the_table_scores_with_mass_unknown(
    tmp_path: Path,
) -> None:
    async with Client(build_server(tmp_path)) as client:
        built = await client.call_tool("build_variant", {"code": PLATE})
        assert built.structured_content is not None
        scored = await client.call_tool(
            "score_variant",
            {"variant_id": built.structured_content["variant_id"], "material_key": "unobtainium"},
        )
    assert not scored.is_error, text_of(scored)
    assert scored.structured_content is not None
    verdicts = {r["check_id"]: r["verdict"] for r in scored.structured_content["results"]}
    assert verdicts == {
        "closed_solid": "pass",
        "interference": "pass",
        "mass": "unknown",
        "extents": "pass",
    }


async def test_the_score_variant_description_claims_no_more_than_the_server_does() -> None:
    description = await listed_description("score_variant")
    assert "stored scorecard" not in description
    assert "store the scorecard" not in description
    assert (
        "while the materials table, the sandbox image and the confirmed requirements are unchanged"
        in description
    )
    assert all(
        kind in description for kind in ("no_brief", "awaiting_confirmation", "against_brief")
    )


async def test_an_unreadable_materials_table_lists_nothing_and_shows_no_host_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    table = tmp_path / "materials.yaml"
    table.write_text("materials: []\n")
    table.chmod(0o000)
    monkeypatch.setattr(load_materials, "__defaults__", (table,))
    async with Client(build_server(tmp_path)) as client:
        result = await client.call_tool("list_materials", {})
    table.chmod(0o644)
    assert result.is_error
    assert "PermissionError" in text_of(result)
    assert str(tmp_path) not in text_of(result)
    assert str(table) in caplog.text


async def test_the_server_tells_every_client_that_only_check_results_are_measurements() -> None:
    async with Client(build_server()) as client:
        instructions = client.instructions
    assert instructions == " ".join(
        (
            RULE,
            BUILD_FIRST,
            CHANGES,
            OPTIONS,
            CONTEXT_PARTS,
            HOLES,
            MATERIAL,
            DEEPER_ANALYSIS,
            RESEARCH,
            NOT_VERIFIED,
        )
    )
    assert (await listed_description("score_variant")).endswith(f"{RULE} {NOT_VERIFIED}")
