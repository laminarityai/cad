import re
from collections.abc import Sequence
from typing import Final

from cad.briefs import store as briefs
from cad.confirmations.answers import Edit, ItemKindName, ItemRef
from cad.confirmations.items import Changes, Refused, Row, Section
from cad.context_parts.ingest import Facts
from cad.context_parts.store import Stored, stored_parts
from cad.projects.model import ProjectId, TamperedProject, parse_project_id
from cad.records.roots import Roots

SLOT: Final = re.compile(r"([a-z]+-[0-9a-f]{16})/context_part/([1-9][0-9]{0,3})")
TITLE: Final = "A part your design must fit with"
DECIDES: Final = (
    "The fit check fails a variant that overlaps it and measures the clearance between them"
)
NO_EDIT: Final = (
    "A part your design must fit with has no number to change. If it is the wrong part, "
    "decline it and say why in the note."
)


class ContextParts:
    def __init__(self, roots: Roots) -> None:
        self._roots = roots

    @property
    def name(self) -> ItemKindName:
        return "context_part"

    def pending(self, project: ProjectId) -> tuple[ItemRef, ...]:
        parts = stored_parts(self._roots.projects, project)
        return tuple(part.ref for part in parts if part.outcome == "waiting")

    def section(self, ref: ItemRef) -> Section:
        part = self._part_at(ref)
        record = part.record
        span = record.origin
        if record.brief_id is None or span is None:
            raise TamperedProject(f"context part {record.id} was uploaded and never waits")
        brief = briefs.read_brief(self._roots, record.brief_id)
        if brief.project != record.project or span.end > len(brief.text):
            raise TamperedProject(f"context part {record.id} does not match brief {brief.id}")
        origin = record.name
        if _confirmed_before(self._roots, part) is not None:
            origin += ", a newer revision of the part you confirmed"
        row = Row(
            headline=f"{origin}: {_size(record.facts)}",
            quote=brief.text[span.start : span.end],
            decides=DECIDES,
        )
        return Section(title=TITLE, brief_id=brief.id, context=brief.text, rows=(row,))

    def edit(self, ref: ItemRef, edits: Sequence[Edit]) -> Refused | Changes:
        return Refused(NO_EDIT)

    def _part_at(self, ref: ItemRef) -> Stored:
        match = SLOT.fullmatch(ref.slot)
        if match is None:
            raise TamperedProject(f"no context part is stored at {ref.slot!r}")
        parts = stored_parts(self._roots.projects, parse_project_id(match.group(1)))
        number = int(match.group(2))
        if not 1 <= number <= len(parts) or parts[number - 1].ref != ref:
            raise TamperedProject(f"context part {ref.slot} changed since the page opened")
        return parts[number - 1]


def _size(facts: Facts) -> str:
    x, y, z = (high - low for low, high in zip(facts.box_min, facts.box_max, strict=True))
    return f"a box of {x:.6g} by {y:.6g} by {z:.6g} mm"


def _confirmed_before(roots: Roots, part: Stored) -> Stored | None:
    """The confirmed geometry this record would replace, when it updates a part."""
    if part.record.replaces is None:
        return None
    earlier = stored_parts(roots.projects, part.record.project)[: part.number - 1]
    same = [
        one for one in earlier if one.record.id == part.record.id and one.outcome == "confirmed"
    ]
    return same[-1] if same else None
