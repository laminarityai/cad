import inspect
from collections.abc import Callable
from dataclasses import dataclass
from enum import Flag, auto
from pathlib import Path
from typing import TypeAliasType

from pydantic import BaseModel, ConfigDict

from cad.confirmations.ballot import Desk
from cad.context_parts.store import Ingest
from cad.records.roots import Roots


class Audience(Flag):
    AGENT = auto()
    PERSON = auto()


BOTH = Audience.AGENT | Audience.PERSON


@dataclass(frozen=True, slots=True)
class Tenant:
    roots: Roots
    variants: Path
    desk: Desk
    ingest: Ingest


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


def operation[I: Input](
    *,
    name: str,
    audience: Audience,
    description: str,
    input: type[I],
    output: type[BaseModel] | TypeAliasType,
    run: Callable[[Tenant, I], object],
) -> Operation:
    def call(tenant: Tenant, arguments: Input) -> object:
        assert isinstance(arguments, input)
        return run(tenant, arguments)

    return Operation(
        name=name,
        audience=audience,
        description=description,
        input=input,
        output=output,
        run=call,
        is_async=inspect.iscoroutinefunction(run),
    )
