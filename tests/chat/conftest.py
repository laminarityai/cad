from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from cad.accounts.local import LocalIssuer
from cad.chat.model import Model
from cad.confirmations.waiting import Door
from cad.confirmations.web import LocalSignIn
from cad.context_parts.ingest import ingest
from cad.operations.tenants import Tenants
from cad.server.hosted import build_app
from tests.chat.support import BASE, Chat, script, step
from tests.conftest import Person, local_pages


@pytest.fixture
def local(tmp_path: Path) -> LocalIssuer:
    return LocalIssuer.open(tmp_path, BASE)


@pytest.fixture
def tenants(tmp_path: Path, person: Person) -> Tenants:
    person.answer = "confirm"
    door = Door(open_page=local_pages(person, lambda account: tenants.of(account)), wait_seconds=5)
    tenants = Tenants(tmp_path / "accounts", 600, door, ingest)
    return tenants


@pytest.fixture
def model() -> Model:
    return script(step("Hello."))


@pytest.fixture
async def chat(local: LocalIssuer, tenants: Tenants, model: Model) -> AsyncIterator[Chat]:
    app = build_app(local.issuer(), tenants, LocalSignIn(local), model)
    async with app.router.lifespan_context(app):
        yield Chat(app, local, tenants)
