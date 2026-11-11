import inspect
import uuid
from collections.abc import Awaitable, Callable, Generator, Iterable
from contextlib import contextmanager, suppress
from typing import Annotated, Any, Final, cast

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from mcp.shared.exceptions import MCPError
from mcp_types import ElicitRequest, ElicitRequestURLParams, InputRequiredResult
from mcp_types.version import is_version_at_least

from cad.briefs.store import BriefRefused
from cad.operations.model import Audience, Operation, Tenant
from cad.projects.model import ProjectRefused
from cad.records.signed import StoreUnusable
from cad.sandbox.meter import metered
from cad.sandbox.outcome import SandboxUnavailable
from cad.selections.model import SelectionRefused, UnknownSelection
from cad.variant_sets.model import SetRefused
from cad.variants.entry import VariantRefused

type Call = Callable[..., object]
type TenantOf = Callable[[], Tenant]

REFUSALS: Final = (
    VariantRefused,
    BriefRefused,
    ProjectRefused,
    SetRefused,
    UnknownSelection,
    SelectionRefused,
)
UNAVAILABLE: Final = (SandboxUnavailable, StoreUnusable)
STATELESS: Final = "2026-07-28"
CONTEXT: Final = "ctx"
OPEN_PAGE: Final = (
    "Open the confirmation page in the web app to confirm or decline what the agent proposed."
)


def agent_operations(operations: Iterable[Operation]) -> tuple[Operation, ...]:
    return tuple(one for one in operations if Audience.AGENT in one.audience)


def tools(tenant_of: TenantOf, operations: Iterable[Operation]) -> list[Tool]:
    """`tenant_of` names the tenant of the call being served: the one account of a stdio server,
    or the account of the verified token on `/mcp`."""
    return [_strict(_tool(tenant_of, one)) for one in agent_operations(operations)]


def _tool(tenant_of: TenantOf, one: Operation) -> Tool:
    if one.page is not None:
        call = _asking(tenant_of, one)
        return Tool.from_function(
            call, name=one.name, description=one.description, context_kwarg=CONTEXT
        )
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


def _asking(tenant_of: TenantOf, one: Operation) -> Call:
    """Before it runs, the call asks a client that declared URL elicitation to open the page.
    The client's accept, decline or cancel is never an answer: only the page records one."""
    page = one.page
    assert page is not None and one.is_async

    async def asking(ctx: Context[Any, Any], **arguments: object) -> object:
        tenant = tenant_of()
        parsed = one.input(**arguments)
        with agent_facing():
            url = page(tenant, parsed) if _opens_urls(ctx) else None
        if url is not None and ctx.request_state is None:
            asked = await _ask_to_open(ctx, url)
            if asked is not None:
                return asked
        with agent_facing(), metered(tenant.meter):
            return await cast(Awaitable[object], one.run(tenant, parsed))

    asking.__dict__["__signature__"] = _signature(one)
    asking.__name__ = one.name
    return asking


def _opens_urls(ctx: Context[Any, Any]) -> bool:
    declared = ctx.client_capabilities
    return (
        declared is not None
        and declared.elicitation is not None
        and declared.elicitation.url is not None
    )


async def _ask_to_open(ctx: Context[Any, Any], url: str) -> InputRequiredResult | None:
    """On the stateless protocol the ask is an input request and the client retries; before it,
    the server sends the request and waits for the client's reply, whatever it is."""
    version = ctx.protocol_version
    if version is not None and is_version_at_least(version, STATELESS):
        ask = ElicitRequest(params=ElicitRequestURLParams(message=OPEN_PAGE, url=url))
        return InputRequiredResult(input_requests={"page": ask}, request_state="page")
    with suppress(MCPError):
        await ctx.elicit_url(OPEN_PAGE, url, uuid.uuid4().hex)
    return None


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
