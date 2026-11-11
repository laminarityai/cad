"""The base every immutable record derives from: a field cannot be set after the record is built,
and an unknown field in the input is refused."""

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
