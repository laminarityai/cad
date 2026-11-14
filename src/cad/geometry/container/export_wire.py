from typing import Literal, TypedDict


class ExportedWire(TypedDict):
    """The three files of one BREP, each base64 encoded."""

    kind: Literal["exported"]
    step: str
    stl: str
    threemf: str
    colours_left_out: str | None


class ExportUnreadableWire(TypedDict):
    kind: Literal["unreadable"]
    reason: str


class ExportTooLargeWire(TypedDict):
    kind: Literal["too_large"]
    reason: str


type ExportReport = ExportedWire | ExportUnreadableWire | ExportTooLargeWire
