"""The one message the in-container runner writes to its report channel.

Every field is a claim by code the agent controls. The host validates it against these types,
caps each string, decodes the files itself, and writes every message the agent reads.
"""

from typing import Literal, TypedDict


class BuiltReport(TypedDict):
    kind: Literal["built"]
    brep: str
    step: str


class FailedReport(TypedDict):
    kind: Literal["build_failed"]
    error: str
    traceback: str


class NoResultReport(TypedDict):
    kind: Literal["no_result"]
    found: str | None
    """The type name of `result`, or None when the code never assigned it."""


type Report = BuiltReport | FailedReport | NoResultReport
