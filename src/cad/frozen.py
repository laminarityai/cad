"""The base every immutable record derives from: a field cannot be set after the record is built,
and an unknown field in the input is refused.

Derive from `FrozenArbitrary` only when a field's type is one pydantic has no schema for.
"""

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FrozenArbitrary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
