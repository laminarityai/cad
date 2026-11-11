import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from cad.sandbox.image import BUILD, image_tag
from cad.server.app import build_server
from cad.variants import entry, store

pytestmark = [pytest.mark.anyio, pytest.mark.docker]

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
NO_DOCKER = "unix:///nonexistent/docker.sock"
TOOLS = ("build_variant", "score_variant")


@pytest.fixture(scope="module")
def stored(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    root = tmp_path_factory.mktemp("variants")
    return root, store.build_variant(PLATE, root).variant_id


async def call(tool: str, root: Path, variant_id: str, nonce: str) -> str:
    arguments = (
        {"code": f"{PLATE}# {nonce}\n"}
        if tool == "build_variant"
        else {"variant_id": variant_id, "material_key": "prusament-pla"}
    )
    async with Client(build_server(variants_root=root)) as client:
        result: Any = await client.call_tool(tool, arguments)
    assert result.is_error
    return result.content[0].model_dump()["text"]


@pytest.mark.parametrize("tool", TOOLS)
async def test_unreachable_docker_names_no_socket_path(
    tool: str,
    stored: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await call(tool, *stored, "unreachable")
    assert text == f"Error executing tool {tool}: docker is not reachable"
    assert "/nonexistent/docker.sock" in caplog.text


@pytest.mark.parametrize("tool", TOOLS)
async def test_a_mount_docker_refuses_names_no_mount_path(
    tool: str,
    stored: tuple[Path, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    missing = tmp_path / "missing-mount"
    shim = tmp_path / "bin" / "docker"
    shim.parent.mkdir()
    shim.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = run ]; then shift; set -- run --mount '
        f'"type=bind,source={missing},target=/missing,readonly" "$@"; fi\n'
        f'exec {shutil.which("docker")} "$@"\n'
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim.parent}{os.pathsep}{os.environ['PATH']}")
    text = await call(tool, *stored, "bad mount")
    assert text == f"Error executing tool {tool}: docker could not run the sandbox"
    assert "missing-mount" in caplog.text


async def test_an_unusable_store_names_the_variant_and_the_kind_and_no_host_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    locked = tmp_path / "locked"
    (locked / "usage").mkdir(parents=True)
    locked.chmod(0o555)
    root = locked / "variants"
    text = await call("build_variant", root, "", "locked store")
    locked.chmod(0o755)
    vid = entry.variant_id(f"{PLATE}# locked store\n", image_tag(BUILD))
    assert text == (
        f"Error executing tool build_variant: cannot use the variant store for variant {vid}: "
        "PermissionError"
    )
    assert str(root) in caplog.text
