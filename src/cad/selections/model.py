"""A selection: the part of one revision's geometry the person pointed at in the 3D view.

The viewer sends what the person picked, as face and edge numbers of the BREP it drew. The server
resolves them against that revision's geometry and signs a `SelectionRecord`, as it signs page
answers (ADR-0003, ADR-0004). The agent holds only the record's `sel-` id. It can read what the
record covers but can never make one, so it never names a face (ADR-0007). A selection is where a
change goes, never a load or a check input.
"""

import re
from datetime import datetime
from typing import Annotated, Final, Literal, NewType, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    StringConstraints,
    model_validator,
)

MAX_PICKS: Final = 64
SELECTION_ID: Final = re.compile(r"^sel-[0-9a-f]{16}$")

SelectionId = NewType("SelectionId", str)
type Vec = tuple[float, float, float]


class SelectionRefused(Exception):
    """The viewer's pick does not resolve against the revision it names. Nothing was signed."""


class UnknownSelection(Exception):
    pass


def parse_selection_id(raw: str) -> SelectionId:
    if SELECTION_ID.fullmatch(raw) is None:
        raise UnknownSelection(f"a selection id is sel- and 16 lowercase hex digits, not {raw!r}")
    return SelectionId(raw)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


type Index = NonNegativeInt


class Picked(_Frozen):
    """What the person picked in the viewer: faces and edges of the variant on screen, numbered
    as its mesh numbers them, or the whole part."""

    variant_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]
    faces: tuple[Index, ...] = Field(default=(), max_length=MAX_PICKS)
    edges: tuple[Index, ...] = Field(default=(), max_length=MAX_PICKS)
    part: bool = False

    @model_validator(mode="after")
    def _one_kind_of_pick(self) -> Self:
        if self.part and (self.faces or self.edges):
            raise ValueError("a whole-part pick names no faces or edges")
        if not self.part and not self.faces and not self.edges:
            raise ValueError("pick a face, an edge or the whole part")
        if len(set(self.faces)) != len(self.faces) or len(set(self.edges)) != len(self.edges):
            raise ValueError("each face and edge is picked once")
        return self


class Neighbour(_Frozen):
    """A face next to a picked face or edge, described so the agent can find it in its code."""

    face: int
    type: str
    normal: Vec | None
    radius_mm: float | None


class SelectedFace(_Frozen):
    face: int
    type: str
    area_mm2: float
    center_mm: Vec
    normal: Vec | None
    radius_mm: float | None
    axis: Vec | None
    adjacent: tuple[Neighbour, ...]


class SelectedEdge(_Frozen):
    edge: int
    type: str
    length_mm: float
    center_mm: Vec
    direction: Vec | None
    radius_mm: float | None
    between: tuple[Neighbour, ...]


class BoundingBox(_Frozen):
    min_mm: Vec
    max_mm: Vec


class SelectedPart(_Frozen):
    faces: int
    edges: int
    bounding_box: BoundingBox


class SelectionRecord(_Frozen):
    """One signed selection, bound to the revision's BREP by its sha256. `made_by` names the
    route that made it; the viewer is the only one so far (#79 names the words route)."""

    selection_id: str
    made_by: Literal["viewer"] = "viewer"
    project_id: str
    brief_id: str
    slot: int
    revision: int
    variant_id: str
    brep_sha256: str
    faces: tuple[SelectedFace, ...] = ()
    edges: tuple[SelectedEdge, ...] = ()
    part: SelectedPart | None = None
    made_at: datetime


class SelectionNote(_Frozen):
    """What the transcript keeps of a message's selection: the id the agent passes on and the
    words the chat shows, such as 2 faces."""

    selection_id: str
    summary: str
    brief_id: str
    slot: int
    revision: int
