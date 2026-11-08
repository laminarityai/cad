from collections.abc import Generator
from contextlib import contextmanager

from mcp.server.mcpserver.exceptions import ToolError

from cad.briefs.records import BriefStoreUnusable
from cad.briefs.store import BriefRefused
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants.entry import VariantRefused


@contextmanager
def agent_facing() -> Generator[None]:
    try:
        yield
    except (VariantRefused, BriefRefused) as error:
        raise ToolError(f"{type(error).__name__}: {error}") from error
    except (SandboxUnavailable, BriefStoreUnusable) as error:
        raise ToolError(str(error)) from error
