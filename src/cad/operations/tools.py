import inspect
from collections.abc import Awaitable, Callable, Generator, Iterable
from contextlib import contextmanager
from typing import Annotated, cast

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool

from cad.briefs.store import BriefRefused
from cad.operations.model import Audience, Operation, Tenant
from cad.projects.model import ProjectRefused
from cad.records.signed import StoreUnusable
from cad.sandbox.outcome import SandboxUnavailable
from cad.variant_sets.model import SetRefused
from cad.variants.entry import VariantRefused

type Call = Callable[..., object]


def agent_operations(operations: Iterable[Operation]) -> tuple[Operation, ...]:
    return tuple(one for one in operations if Audience.AGENT in one.audience)


def tools(tenant: Tenant, operations: Iterable[Operation]) -> list[Tool]:
    return [_strict(_tool(tenant, one)) for one in agent_operations(operations)]


def _tool(tenant: Tenant, one: Operation) -> Tool:
    return Tool.from_function(_call(tenant, one), name=one.name, description=one.description)


def _call(tenant: Tenant, one: Operation) -> Call:
    """The SDK reads a tool's arguments from `__signature__`, set from the operation's input."""

    def sync(**arguments: object) -> object:
        with agent_facing():
            return one.run(tenant, one.input(**arguments))

    async def asynchronous(**arguments: object) -> object:
        with agent_facing():
            return await cast(Awaitable[object], one.run(tenant, one.input(**arguments)))

    call = asynchronous if one.is_async else sync
    call.__dict__["__signature__"] = _signature(one)
    call.__name__ = one.name
    return call


@contextmanager
def agent_facing() -> Generator[None]:
    try:
        yield
    except (VariantRefused, BriefRefused, ProjectRefused, SetRefused) as error:
        raise ToolError(f"{type(error).__name__}: {error}") from error
    except (SandboxUnavailable, StoreUnusable) as error:
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
