from collections.abc import AsyncIterator

import pytest

from cad.accounts.local import LocalIssuer
from cad.chat.model import Model
from cad.confirmations.web import LocalSignIn
from cad.operations.tenants import Tenants
from cad.server.hosted import build_app
from tests.support.chat import Chat, script, step


@pytest.fixture
def chat_tenants(confirming_tenants: Tenants) -> Tenants:
    """The accounts the `chat` fixture serves. A test file that needs other ones overrides this."""
    return confirming_tenants


@pytest.fixture
def model() -> Model:
    return script(step("Hello."))


@pytest.fixture
async def chat(local: LocalIssuer, chat_tenants: Tenants, model: Model) -> AsyncIterator[Chat]:
    app = build_app(local.issuer(), chat_tenants, LocalSignIn(local), model)
    async with app.router.lifespan_context(app):
        yield Chat(app, local, chat_tenants)
