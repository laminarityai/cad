import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Final

import uvicorn
from mcp.server import MCPServer
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId
from cad.accounts.tokens import Verifier
from cad.confirmations.waiting import OS_OPEN, WAIT_SECONDS, Door, Opener, sign_in_opener
from cad.confirmations.web import LocalSignIn, confirm_routes
from cad.context_parts.ingest import ingest as read_part
from cad.context_parts.store import Ingest
from cad.geometry.store import GEOMETRY_ROOT
from cad.operations.guidance import INSTRUCTIONS
from cad.operations.model import Tenant
from cad.operations.registry import OPERATIONS
from cad.operations.tenants import open_tenant
from cad.operations.tools import tools
from cad.projects.model import ProjectId
from cad.records.roots import HOME_ROOTS, Roots
from cad.variants import entry

LOCAL: Final = AccountId("local")
LOOPBACK: Final = "127.0.0.1"


class LocalPage:
    """The stdio server's confirmation page: the web app's page routes on 127.0.0.1, on a port
    the system picks, started when the first page opens. Its issuer's key lives only in this
    process, so only the link handed to the opener signs the person in."""

    def __init__(self, opener: Opener, tenant: Callable[[], Tenant]) -> None:
        self._opener = opener
        self._tenant = tenant
        self._lock = threading.Lock()
        self._issuer: LocalIssuer | None = None

    def open(self, account: AccountId, project: ProjectId) -> None:
        sign_in_opener(self._started(), self._opener)(account, project)

    def _started(self) -> LocalIssuer:
        with self._lock:
            if self._issuer is None:
                listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listening.bind((LOOPBACK, 0))
                listening.listen(64)
                issuer = LocalIssuer.in_memory(f"http://{LOOPBACK}:{listening.getsockname()[1]}")
                routes = confirm_routes(
                    Verifier(issuer.issuer()),
                    lambda _: self._tenant(),
                    issuer.origin,
                    LocalSignIn(issuer),
                )
                config = uvicorn.Config(
                    Starlette(routes=routes), log_level="warning", access_log=False, lifespan="off"
                )
                server = uvicorn.Server(config)
                threading.Thread(target=server.run, args=([listening],), daemon=True).start()
                self._issuer = issuer
            return self._issuer


def build_server(
    variants_root: Path = entry.VARIANTS_ROOT,
    roots: Roots = HOME_ROOTS,
    opener: Opener = OS_OPEN,
    wait_seconds: float = WAIT_SECONDS,
    ingest: Ingest = read_part,
    geometry_root: Path = GEOMETRY_ROOT,
) -> MCPServer:
    """The stdio server: one local account in `~/.cad`, metered with no cap."""
    page = LocalPage(opener, lambda: tenant)
    door = Door(open_page=page.open, wait_seconds=wait_seconds)
    tenant = open_tenant(LOCAL, roots, variants_root, geometry_root, None, door, ingest)
    return MCPServer("cad", instructions=INSTRUCTIONS, tools=tools(lambda: tenant, OPERATIONS))
