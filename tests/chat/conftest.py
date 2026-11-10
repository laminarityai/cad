from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from cad.accounts.local import LocalIssuer
from cad.accounts.tenants import Tenants
from cad.chat.model import Model
from cad.context_parts.ingest import ingest
from cad.server.hosted import build_app
from tests.chat.support import BASE, Chat, confirm, script, step


@pytest.fixture
def local(tmp_path: Path) -> LocalIssuer:
    return LocalIssuer.open(tmp_path, BASE)


@pytest.fixture
def tenants(tmp_path: Path) -> Tenants:
    return Tenants(tmp_path / "accounts", 600, confirm, 5, ingest)


@pytest.fixture
def model() -> Model:
    return script(step("Hello."))


@pytest.fixture
async def chat(local: LocalIssuer, tenants: Tenants, model: Model) -> AsyncIterator[Chat]:
    app = build_app(local.issuer(), tenants, model)
    async with app.router.lifespan_context(app):
        yield Chat(app, local, tenants)
