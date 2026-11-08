from typing import Literal

from pydantic import BaseModel, ConfigDict


class Waiting(BaseModel):
    """A requirement whose deciding check is still running in the background. It has no verdict
    yet: score the variant again with the same arguments to wait for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["waiting"] = "waiting"
    requirement_id: str
    statement: str
    check_id: str
