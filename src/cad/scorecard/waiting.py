from typing import Literal

from pydantic import Field

from cad.frozen import Frozen


class Waiting(Frozen):
    """A requirement whose deciding check is still running in the background. It has no verdict
    yet: score the variant again with the same arguments to wait for it."""

    kind: Literal["waiting"] = "waiting"
    requirement_id: str
    statement: str
    check_id: str
    load_case: Literal["described"] | None = Field(default=None, exclude_if=lambda one: one is None)
