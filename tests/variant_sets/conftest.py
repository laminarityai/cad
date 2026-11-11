from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from mcp import Client

from cad.records.roots import Roots
from cad.server.app import build_server
from tests.support.browser import Person
from tests.support.variant_set_session import Session


@pytest.fixture
async def s(tmp_path: Path) -> AsyncIterator[Session]:
    person = Person(answer="confirm")
    server = build_server(
        tmp_path / "variants",
        Roots(tmp_path / "briefs", tmp_path / "projects"),
        opener=person,
        wait_seconds=5,
    )
    async with Client(server) as client:
        yield Session(client, tmp_path)
