from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Built, TimedOut
from cad.server.app import build_server
from cad.variants.entry import variant_id
from cad.variants.store import BuildResult, build_variant

PARTS = {path.stem: path.read_text() for path in (Path(__file__).parent / "parts").glob("*.py")}
NO_DOCKER = "unix:///nonexistent/docker.sock"


@pytest.fixture(scope="module")
def built_parts(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Mapping[str, BuildResult]]:
    root = tmp_path_factory.mktemp("variants")
    with ThreadPoolExecutor(4) as pool:
        results = pool.map(partial(build_variant, root=root), PARTS.values())
        return root, dict(zip(PARTS, results, strict=True))


def test_there_are_ten_reference_parts() -> None:
    assert len(PARTS) == 10


@pytest.mark.parametrize("part", sorted(PARTS))
@pytest.mark.docker
def test_reference_part_builds_and_stores_its_files(
    part: str, built_parts: tuple[Path, Mapping[str, BuildResult]]
) -> None:
    root, results = built_parts
    result = results[part]
    assert result.outcome == Built(), result.output
    stored = root / result.variant_id
    assert sorted(path.name for path in stored.iterdir()) == [
        "build.json",
        "build.mac",
        "code.py",
        "result.brep",
    ]
    assert (stored / "code.py").read_text() == PARTS[part]


@pytest.mark.docker
def test_a_timed_out_build_is_not_stored(tmp_path: Path) -> None:
    result = build_variant("while True:\n    pass\n", tmp_path, wall_seconds=2)
    assert result.outcome == TimedOut(limit_seconds=2)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.docker
def test_a_changed_comment_is_a_new_variant(tmp_path: Path) -> None:
    first = build_variant("x = 1\n", tmp_path)
    second = build_variant("x = 1\n# again\n", tmp_path)
    assert first.variant_id != second.variant_id


async def call(root: Path, code: str) -> Any:
    async with Client(build_server(variants_root=root)) as client:
        return await client.call_tool("build_variant", {"code": code})


def error_text(result: Any) -> str:
    assert result.is_error
    return result.content[0].model_dump()["text"]


@pytest.mark.anyio
@pytest.mark.docker
async def test_plate_over_mcp_is_built_with_a_brep_and_no_step_file(tmp_path: Path) -> None:
    result = await call(tmp_path, PARTS["plate"])
    assert not result.is_error
    assert result.structured_content["outcome"] == {"kind": "built"}
    stored = tmp_path / result.structured_content["variant_id"]
    assert (stored / "result.brep").is_file()
    assert not (stored / "result.step").exists()


@pytest.mark.anyio
@pytest.mark.docker
async def test_the_same_code_twice_is_one_variant_built_once(tmp_path: Path) -> None:
    code = "import random\nprint(random.random())\n"
    first = await call(tmp_path, code)
    second = await call(tmp_path, code)
    assert second.structured_content == first.structured_content
    assert [path.name for path in tmp_path.iterdir()] == [first.structured_content["variant_id"]]


@pytest.mark.anyio
@pytest.mark.docker
async def test_a_stored_variant_is_returned_while_docker_is_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await call(tmp_path, "x = 1\n")
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    second = await call(tmp_path, "x = 1\n")
    assert second.structured_content == first.structured_content


@pytest.mark.anyio
@pytest.mark.docker
async def test_a_name_error_names_the_missing_name(tmp_path: Path) -> None:
    code = "from build123d import *\nresult = Box(1, 1, 1, align=Alignment.CENTER)\n"
    outcome = (await call(tmp_path, code)).structured_content["outcome"]
    assert outcome["kind"] == "build_failed"
    assert outcome["error"] == "NameError: name 'Alignment' is not defined"
    assert "Alignment.CENTER" in outcome["traceback"]


@pytest.mark.anyio
@pytest.mark.docker
async def test_code_that_never_assigns_result_names_the_contract(tmp_path: Path) -> None:
    outcome = (await call(tmp_path, "x = 1\n")).structured_content["outcome"]
    assert outcome == {
        "kind": "no_result",
        "reason": "the code never assigned `result`; assign the final shape to `result`",
    }


@pytest.mark.anyio
async def test_code_over_the_size_limit_is_rejected_before_it_runs(tmp_path: Path) -> None:
    text = error_text(await call(tmp_path, "#" * (256 * 1024 + 1)))
    assert "at most 262144 characters" in text
    assert list(tmp_path.iterdir()) == []


@pytest.mark.anyio
async def test_a_corrupt_stored_build_is_a_one_line_tool_error(tmp_path: Path) -> None:
    stored = tmp_path / variant_id("x = 1\n", image_tag(BUILD))
    stored.mkdir()
    (stored / "build.json").write_text('{"outcome": {"kind": "built"}, "output": ')
    assert error_text(await call(tmp_path, "x = 1\n")) == (
        "Error executing tool build_variant: "
        f"variant {stored.name}'s build record failed the server's integrity check; change its "
        "code, even by a comment, and build it as a new variant"
    )
