from dataclasses import dataclass
from functools import cache

from cad.auto.bounds import bounds_conflicts, unweighed
from cad.auto.model import Bounds, NotChecked
from cad.briefs import store
from cad.briefs.model import MadeOf, Requirement
from cad.briefs.origins import quoted
from cad.briefs.store import BriefState, Status
from cad.briefs.words import describe
from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId
from cad.records.roots import Roots
from cad.research.overlay import project_table
from cad.tables.materials import MaterialsTable, UnknownMaterial, load_materials


@cache
def _cached_git_table() -> MaterialsTable:
    return load_materials()


@dataclass(frozen=True, slots=True)
class Cited:
    headline: str
    quote: str
    source: str


@dataclass(frozen=True, slots=True)
class Conflict:
    """Requirements no design can meet together, or, when `unchecked`, a pair that is not
    checked yet because a value it needs is unknown. An unchecked one claims no conflict."""

    statement: str
    cited: tuple[Cited, ...]
    researched: bool
    unchecked: bool = False


def conflicts(roots: Roots, project: ProjectId) -> tuple[Conflict, ...]:
    table: MaterialsTable | None = None
    found: list[Conflict] = []
    for brief_id in project_briefs(roots, project):
        state = store.read_state(roots, brief_id)
        waiting = _waiting(state)
        if not waiting:
            continue
        table = table or project_table(_cached_git_table(), roots.projects, project).table
        found.extend(_conflict(state, bounds, waiting) for bounds in _bounds(waiting, table))
        note = _unweighed(waiting, table)
        if note is not None:
            found.append(_note(state, note, waiting))
    return tuple(found)


def _waiting(state: BriefState) -> tuple[Requirement, ...]:
    latest = state.latest
    if latest is None or latest.status is not Status.PROPOSED:
        return ()
    return latest.requirements


def _bounds(requirements: tuple[Requirement, ...], table: MaterialsTable) -> tuple[Bounds, ...]:
    try:
        return bounds_conflicts(requirements, table)
    except UnknownMaterial:
        unpinned = tuple(one for one in requirements if not isinstance(one.target, MadeOf))
        return bounds_conflicts(unpinned, table)


def _unweighed(requirements: tuple[Requirement, ...], table: MaterialsTable) -> NotChecked | None:
    try:
        return unweighed(requirements, table)
    except UnknownMaterial:
        return None


def _note(state: BriefState, note: NotChecked, requirements: tuple[Requirement, ...]) -> Conflict:
    named: dict[str, Requirement] = {one.id: one for one in requirements}
    cited = tuple(_cited(named[rid], state.brief.text) for rid in note.requirements)
    return Conflict(note.statement, cited, researched=False, unchecked=True)


def _conflict(state: BriefState, bounds: Bounds, requirements: tuple[Requirement, ...]) -> Conflict:
    named: dict[str, Requirement] = {one.id: one for one in requirements}
    cited = tuple(_cited(named[rid], state.brief.text) for rid in bounds.requirements)
    researched = any(read.basis == "researched" for read in bounds.reads)
    return Conflict(bounds.statement, cited, researched)


def _cited(requirement: Requirement, brief_text: str) -> Cited:
    source, quote = quoted(brief_text, requirement.origin)
    return Cited(describe(requirement), quote, source)
