from pathlib import Path

from mcp.server import MCPServer

from cad.accounts.tenants import open_tenant
from cad.confirmations.ballot import OS_OPEN, WAIT_SECONDS, Opener
from cad.context_parts.ingest import ingest as read_part
from cad.context_parts.store import Ingest
from cad.operations.guidance import INSTRUCTIONS
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
    """The stdio server: one local account in `~/.cad`, metered with no cap."""
    tenant = open_tenant(roots, variants_root, None, opener, wait_seconds, ingest)
    return MCPServer("cad", instructions=INSTRUCTIONS, tools=tools(lambda: tenant, OPERATIONS))
