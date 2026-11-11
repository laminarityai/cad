from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.confirmations.waiting import Door
from cad.confirmations.web import LocalSignIn
from cad.context_parts.ingest import ingest
from cad.operations.tenants import Tenants
from cad.server.hosted import build_app
from tests.support.conversations import BASE


@pytest.fixture
def local(tmp_path: Path) -> LocalIssuer:
    return LocalIssuer.open(tmp_path, BASE)


@pytest.fixture
def tenants(tmp_path: Path) -> Tenants:
    return Tenants(tmp_path / "accounts", 60, Door(wait_seconds=0.3), ingest)


@pytest.fixture
async def app(local: LocalIssuer, tenants: Tenants) -> AsyncIterator[Starlette]:
    app = build_app(local.issuer(), tenants, LocalSignIn(local))
    async with app.router.lifespan_context(app):
        yield app
