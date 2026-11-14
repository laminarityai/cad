"""The one body of the variant a requirement is about, by the exact name its build code gives it.

A requirement with no body reads the whole variant. The field is left out of the record when it is
None, so a requirement stored before bodies keeps its bytes and its id.
"""

from typing import Any

from pydantic import Field


def _whole(body: object) -> bool:
    return body is None


def on_body() -> Any:
    return Field(default=None, exclude_if=_whole)


def per_body(measure: str, body: str | None) -> str:
    """The name a check gives a measure of one body: `mass:plate`, or `hole_diameter:plate:0` for
    the whole variant's `hole_diameter:0`."""
    if body is None:
        return measure
    head, colon, rest = measure.partition(":")
    return f"{head}:{body}{colon}{rest}"
