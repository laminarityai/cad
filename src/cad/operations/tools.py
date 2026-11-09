import inspect
from collections.abc import Awaitable, Callable, Generator, Iterable
from contextlib import contextmanager
from typing import Annotated, Final, cast

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool

from cad.briefs.store import BriefRefused
from cad.operations.model import Audience, Operation, Tenant
from cad.projects.model import ProjectRefused
from cad.records.signed import StoreUnusable
from cad.sandbox.meter import metered
from cad.sandbox.outcome import SandboxUnavailable
from cad.variant_sets.model import SetRefused
from cad.variants.entry import VariantRefused

type Call = Callable[..., object]
type TenantOf = Callable[[], Tenant]

REFUSALS: Final = (VariantRefused, BriefRefused, ProjectRefused, SetRefused)
UNAVAILABLE: Final = (SandboxUnavailable, StoreUnusable)


def agent_operations(operations: Iterable[Operation]) -> tuple[Operation, ...]:
    return tuple(one for one in operations if Audience.AGENT in one.audience)


def tools(tenant_of: TenantOf, operations: Iterable[Operation]) -> list[Tool]:
    """`tenant_of` names the tenant of the call being served: the one account of a stdio server,
    or the account of the verified token on `/mcp`."""
    return [_strict(_tool(tenant_of, one)) for one in agent_operations(operations)]


def _tool(tenant_of: TenantOf, one: Operation) -> Tool:
    return Tool.from_function(_call(tenant_of, one), name=one.name, description=one.description)


def _call(tenant_of: TenantOf, one: Operation) -> Call:
    """The SDK reads a tool's arguments from `__signature__`, set from the operation's input.
    Every container the call starts is charged to its tenant's meter."""

    def sync(**arguments: object) -> object:
        tenant = tenant_of()
        with agent_facing(), metered(tenant.meter):
            return one.run(tenant, one.input(**arguments))

    async def asynchronous(**arguments: object) -> object:
        tenant = tenant_of()
        with agent_facing(), metered(tenant.meter):
            return await cast(Awaitable[object], one.run(tenant, one.input(**arguments)))

    call = asynchronous if one.is_async else sync
    call.__dict__["__signature__"] = _signature(one)
    call.__name__ = one.name
    return call


@contextmanager
def agent_facing() -> Generator[None]:
    try:
        yield
    except REFUSALS as error:
        raise ToolError(f"{type(error).__name__}: {error}") from error
    except UNAVAILABLE as error:
        raise ToolError(str(error)) from error


def _signature(one: Operation) -> inspect.Signature:
    parameters = [
        inspect.Parameter(
            name,
            inspect.Parameter.KEYWORD_ONLY,
            default=inspect.Parameter.empty if field.is_required() else field.default,
            annotation=Annotated[field.annotation, field],
        )
        for name, field in one.input.model_fields.items()
    ]
    return inspect.Signature(parameters, return_annotation=one.output)


def _strict(tool: Tool) -> Tool:
    """Reject arguments the tool does not declare; the SDK ignores them by default."""
    arguments = tool.fn_metadata.arg_model
    arguments.model_config["extra"] = "forbid"
    arguments.model_rebuild(force=True)
    tool.parameters = arguments.model_json_schema(by_alias=True)
    return tool
