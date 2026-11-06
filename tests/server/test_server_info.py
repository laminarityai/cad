import json
import subprocess
import sys

import pytest
from mcp import Client

from cad.server.app import REPO_ROOT, build_server

pytestmark = pytest.mark.anyio


def head_sha() -> str:
    done = subprocess.run(
        ("git", "rev-parse", "HEAD"), capture_output=True, text=True, check=True, cwd=REPO_ROOT
    )
    return done.stdout.strip()


def is_dirty() -> bool:
    done = subprocess.run(
        ("git", "status", "--porcelain"),
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    return bool(done.stdout.strip())


async def test_server_info_names_the_head_sha_python_and_tools() -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("server_info", {})
    assert not result.is_error
    assert result.structured_content == {
        "sha": head_sha(),
        "dirty": is_dirty(),
        "python": sys.version.split()[0],
        "tools": ["build_variant", "list_materials", "score_variant", "server_info"],
    }


async def test_extra_argument_is_a_validation_error() -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("server_info", {"unexpected": 1})
    assert result.is_error
    assert "unexpected" in json.dumps([block.model_dump() for block in result.content])


async def test_unknown_tool_is_an_error_naming_the_tool() -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("no_such_tool", {})
    assert result.is_error
    assert "no_such_tool" in json.dumps([block.model_dump() for block in result.content])
