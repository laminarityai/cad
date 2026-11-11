import inspect
from collections.abc import Callable
from dataclasses import dataclass
from enum import Flag, auto
from pathlib import Path
from typing import Annotated, TypeAliasType

from pydantic import BaseModel, ConfigDict, StringConstraints

from cad.accounts.principal import AccountId
from cad.confirmations.waiting import Bell, Door
from cad.context_parts.store import Ingest
from cad.conversations.model import ConversationId, Mode
from cad.frozen import Frozen
from cad.records.roots import Roots
from cad.sandbox.meter import Meter


class Audience(Flag):
    AGENT = auto()
    PERSON = auto()
    PAGE = auto()


BOTH = Audience.AGENT | Audience.PERSON


@dataclass(frozen=True, slots=True)
class Tenant:
    account: AccountId
    roots: Roots
    variants: Path
    geometry: Path
    conversations: Path
    bell: Bell
    door: Door
    ingest: Ingest
    meter: Meter
    conversation: ConversationId | None = None
    mode: Mode | None = None
    auto_run: str | None = None


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Download(Frozen):
    """What an operation returns when its route answers with a file: the route sends `data` as it
    is, as an attachment saved under `filename`. The pattern keeps a name from breaking the header
    it goes in."""

    filename: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]*$")]
    data: bytes


@dataclass(frozen=True, slots=True)
class Operation:
    name: str
    audience: Audience
    description: str
    input: type[Input]
    output: type[BaseModel] | TypeAliasType
    run: Callable[[Tenant, Input], object]
    is_async: bool
    page: Callable[[Tenant, Input], str | None] | None = None


def operation[I: Input](
    *,
    name: str,
    audience: Audience,
    description: str,
    input: type[I],
    output: type[BaseModel] | TypeAliasType,
    run: Callable[[Tenant, I], object],
    page: Callable[[Tenant, I], str | None] | None = None,
) -> Operation:
    def call(tenant: Tenant, arguments: Input) -> object:
        assert isinstance(arguments, input)
        return run(tenant, arguments)

    def page_of(tenant: Tenant, arguments: Input) -> str | None:
        assert isinstance(arguments, input) and page is not None
        return page(tenant, arguments)

    return Operation(
        name=name,
        audience=audience,
        description=description,
        input=input,
        output=output,
        run=call,
        is_async=inspect.iscoroutinefunction(run),
        page=None if page is None else page_of,
    )
