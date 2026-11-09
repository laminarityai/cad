from collections.abc import Generator
from contextlib import contextmanager

from mcp.server.mcpserver.exceptions import ToolError

from cad.briefs.store import BriefRefused
from cad.projects.model import ProjectRefused
from cad.records.signed import StoreUnusable
from cad.sandbox.outcome import SandboxUnavailable
from cad.tables.materials import KeyInTable
from cad.variant_sets.model import SetRefused
from cad.variants.entry import VariantRefused


@contextmanager
def agent_facing() -> Generator[None]:
    try:
        yield
    except (VariantRefused, BriefRefused, ProjectRefused, SetRefused, KeyInTable) as error:
        raise ToolError(f"{type(error).__name__}: {error}") from error
    except (SandboxUnavailable, StoreUnusable) as error:
        raise ToolError(str(error)) from error
