"""The one map from an agent-facing refusal to a ToolError."""

from collections.abc import Generator
from contextlib import contextmanager

from mcp.server.mcpserver.exceptions import ToolError

from cad.briefs.records import BriefStoreUnusable
from cad.briefs.store import BriefRefused
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants.entry import VariantRefused


@contextmanager
def agent_facing() -> Generator[None]:
    """A refusal the agent can act on keeps its type name, as in "UnknownBrief: ...". A problem
    only the operator can fix gives its message alone, which never names a host path."""
    try:
        yield
    except (VariantRefused, BriefRefused) as error:
        raise ToolError(f"{type(error).__name__}: {error}") from error
    except (SandboxUnavailable, BriefStoreUnusable) as error:
        raise ToolError(str(error)) from error
