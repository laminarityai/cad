"""A snap-fit strain check, the page it cites, and a brief whose stated strain no team check
decides: what the agent_checks tests write, gate and score."""

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from cad.agent_checks.model import CheckDraft
from cad.briefs import store
from cad.briefs.model import Target
from cad.briefs.origins import FileQuote
from cad.briefs.store import Draft
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.research.fetch import FetchFailed, Page
from cad.research.submit import Fetch

GUIDE: Final = "https://plastics.example.com/snap-fit-guide"
TEXT: Final = "A snap-fit lid catch. The arm must flex at most 2% strain when it snaps shut."
STRAIN: Final = "at most 2% strain"
GUIDE_TEXT: Final = (
    "Cantilever snap-fit joints. For a beam of constant cross section the maximum strain is "
    "1.5 times the thickness times the deflection, divided by the length squared. Example: a "
    "beam of thickness 2 mm and length 20 mm, deflected 1 mm, reaches a strain of 0.75 %."
)
EXAMPLE_QUOTE: Final = (
    "a beam of thickness 2 mm and length 20 mm, deflected 1 mm, reaches a strain of 0.75 %"
)
# Reports the arm's thickness, length and deflection from the stored part.
GEOMETRY: Final = """
box = part.bounding_box()
report("h", box.size.Z, "mm")
report("l", box.size.X, "mm")
report("y", box.size.Z / 2, "mm")
"""
UNCHECKED: Final = TypeAdapter[Target](Target).validate_python(
    {"kind": "unchecked", "statement": "the arm flexes at most 2% strain"}
)


def snap_fit(**changes: Any) -> CheckDraft:
    """The check, with any top-level field replaced."""
    draft: dict[str, Any] = {
        "title": "Snap arm strain",
        "measures": "The strain at the root of the snap arm when it deflects by its undercut.",
        "geometry": GEOMETRY,
        "formula": "k * h * y / l**2",
        "inputs": {"k": "source:k", "h": "geometry:h", "l": "geometry:l", "y": "geometry:y"},
        "sources": [
            {
                "name": "k",
                "value": 1.5,
                "unit": "1",
                "url": GUIDE,
                "quote": "the maximum strain is 1.5 times the thickness",
            }
        ],
        "limit": {"comparator": "at_most", "unit": "%"},
        "example": {
            "url": GUIDE,
            "quote": EXAMPLE_QUOTE,
            "inputs": {
                "h": {"value": 2, "unit": "mm"},
                "l": {"value": 20, "unit": "mm"},
                "y": {"value": 1, "unit": "mm"},
            },
            "result": {"value": 0.75, "unit": "%"},
        },
    }
    return CheckDraft.model_validate(draft | changes)


def fetching(pages: Mapping[str, str] | None = None) -> Fetch:
    held = {GUIDE: GUIDE_TEXT} if pages is None else pages
    return lambda url: (
        Page(url, "Snap-fit design guide", held[url], "ab" * 32)
        if url in held
        else FetchFailed(f"{url} answered 404")
    )


def unchecked_brief(roots: Roots, *, from_a_file: bool = False) -> tuple[str, str]:
    """A brief whose one requirement is the unchecked strain, and that requirement's id."""
    brief = store.create_brief(roots, TEXT, new_project_id(), seq=1)
    cited = (
        FileQuote(file_id="file-" + "1" * 16, name="catch.pdf", quote=STRAIN, checked=True)
        if from_a_file
        else None
    )
    proposed = store.propose(roots, brief.id, [Draft(UNCHECKED, STRAIN, cited)])
    [requirement] = proposed.requirements
    return brief.id, requirement.id
