import inspect
from collections.abc import Callable
from dataclasses import dataclass
from enum import Flag, StrEnum, auto
from pathlib import Path
from typing import TypeAliasType

from pydantic import BaseModel, ConfigDict

from cad.accounts.principal import AccountId
from cad.confirmations.waiting import Bell, Door
from cad.context_parts.store import Ingest
from cad.records.roots import Roots
from cad.sandbox.meter import Meter


class Audience(Flag):
    AGENT = auto()
    PERSON = auto()


BOTH = Audience.AGENT | Audience.PERSON


class Mode(StrEnum):
    PLAN = "plan"
    DESIGN = "design"
    AUTO = "auto"
    TEST = "test"


@dataclass(frozen=True, slots=True)
class Tenant:
    account: AccountId
    roots: Roots
    variants: Path
    geometry: Path
    bell: Bell
    door: Door
    ingest: Ingest
    meter: Meter
    # The caller's conversation mode, from the AgentToken our web backend builds (ADR-0010, phase
    # 4 unit 8). None is an outside client, which has no conversation and so cannot run Auto.
    mode: Mode | None = None


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True, slots=True)
class Operation:
    name: str
    audience: Audience
    description: str
    input: type[Input]
    output: type[BaseModel] | TypeAliasType
    run: Callable[[Tenant, Input], object]
    is_async: bool
    # The page this call asks the person's client to open first, if any.
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
