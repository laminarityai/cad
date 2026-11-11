import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from mcp import Client

from cad.records.key import key_path
from cad.records.roots import Roots
from cad.server.app import build_server
from cad.variants.store import build_variant
from tests.support.browser import Person
from tests.support.set_parts import BRACKET, PLATE, THICKER
from tests.support.variant_set_session import Session


@pytest.fixture(scope="session")
def built_parts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The parts these tests build, built once per worker. Each test gets its own copy, so a
    build of one of them is a store hit and every set, brief and record still starts empty."""
    root = tmp_path_factory.mktemp("set-parts") / "variants"
    for code in (PLATE, THICKER, BRACKET):
        build_variant(code, root)
    return root


@pytest.fixture
async def s(tmp_path: Path, built_parts: Path) -> AsyncIterator[Session]:
    shutil.copytree(built_parts, tmp_path / "variants")
    shutil.copy2(key_path(built_parts), key_path(tmp_path / "variants"))
    person = Person(answer="confirm")
    server = build_server(
        tmp_path / "variants",
        Roots(tmp_path / "briefs", tmp_path / "projects"),
        opener=person,
        wait_seconds=5,
    )
    async with Client(server) as client:
        yield Session(client, tmp_path)
