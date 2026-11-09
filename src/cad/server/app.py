from pathlib import Path

from mcp.server import MCPServer

from cad.confirmations import http
from cad.confirmations.ballot import OS_OPEN, WAIT_SECONDS, Desk, Opener
from cad.confirmations.registry import kinds
from cad.context_parts.ingest import ingest as read_part
from cad.context_parts.store import Ingest
from cad.operations.guidance import INSTRUCTIONS
from cad.operations.model import Tenant
from cad.operations.registry import OPERATIONS
from cad.operations.tools import tools
from cad.records.roots import HOME_ROOTS, Roots
from cad.variants import entry


def build_server(
    variants_root: Path = entry.VARIANTS_ROOT,
    roots: Roots = HOME_ROOTS,
    opener: Opener = OS_OPEN,
    wait_seconds: float = WAIT_SECONDS,
    ingest: Ingest = read_part,
) -> MCPServer:
    desk = Desk(roots, kinds(roots), opener, serve=http.serve, wait_seconds=wait_seconds)
    tenant = Tenant(roots=roots, variants=variants_root, desk=desk, ingest=ingest)
    return MCPServer("cad", instructions=INSTRUCTIONS, tools=tools(tenant, OPERATIONS))
