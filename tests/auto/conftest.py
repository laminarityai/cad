from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mcp import Client
from mcp.server import MCPServer

from cad.confirmations.waiting import Bell, Door
from cad.context_parts.ingest import ingest
from cad.conversations import store
from cad.conversations.model import ConversationId
from cad.operations.model import Tenant
from cad.operations.registry import OPERATIONS
from cad.operations.tenants import bind
from cad.operations.tools import tools
from cad.records.roots import Roots
from cad.server.app import LOCAL, LocalPage
from tests.support.auto_session import Ledger, Session

if TYPE_CHECKING:
    from tests.support.browser import Person


@pytest.fixture
def meter() -> Ledger:
    return Ledger()


@pytest.fixture
async def s(tmp_path: Path, meter: Ledger, person: "Person") -> AsyncIterator[Session]:
    person.answer = "confirm"
    roots = Roots(tmp_path / "briefs", tmp_path / "projects")
    page = LocalPage(person, lambda: tenant)
    tenant = Tenant(
        account=LOCAL,
        roots=roots,
        variants=tmp_path / "variants",
        geometry=tmp_path / "geometry",
        conversations=tmp_path / "conversations",
        bell=Bell(),
        door=Door(open_page=page.open, wait_seconds=5),
        ingest=ingest,
        meter=meter,
    )
    cid = ConversationId("c1")
    store.create(tenant.conversations, cid)
    served = tools(lambda: bind(tenant, cid), OPERATIONS)
    async with Client(MCPServer("cad", tools=served)) as client:
        yield Session(client, tenant, meter, cid)
