"""The gates `write_check` runs before any variant exists (ADR-0011): blind, form and units.

Each returns the reason it refuses, or what it found. The worked example is in `example`, and the
repeat-and-turn gate, which needs the sandbox, is in `probes`.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from cad.agent_checks.formula import Dimension, Formula, dimension, dimension_of, parse
from cad.agent_checks.model import (
    UNITS,
    Bound,
    CheckDraft,
    GeometryInput,
    MaterialInput,
    SourceInput,
    TeamInput,
    parse_binding,
)
from cad.briefs import store as briefs
from cad.briefs.bindable import BINDABLE
from cad.briefs.model import Requirement, Unchecked
from cad.briefs.origins import quoted
from cad.projects.model import ProjectId
from cad.records.roots import Roots
from cad.tables.fields import FIELDS
from cad.variant_sets.store import project_slots


@dataclass(frozen=True, slots=True)
class Shaped:
    formula: Formula
    bound: tuple[Bound, ...]


@dataclass(frozen=True, slots=True)
class WrittenFor:
    requirement: Requirement
    source: str
    words: str


def blind(roots: Roots, project: ProjectId, brief_id: str) -> str | None:
    """G0. A check is written before any variant of its brief exists."""
    slots = sorted(
        member.slot
        for key, member in project_slots(roots.projects, project)
        if key.brief_id == brief_id
    )
    if not slots:
        return None
    return (
        f"brief {brief_id} already holds variants in slots {', '.join(map(str, slots))}: an "
        "agent-written check is written only before any variant of its brief exists"
    )


def written_for(roots: Roots, brief_id: str, requirement_id: str) -> WrittenFor | str:
    """The unchecked requirement of the brief's newest or confirmed proposal the check is for."""
    state = briefs.read_state(roots, brief_id)
    held = [
        *(state.latest.requirements if state.latest else ()),
        *(state.confirmed.requirements if state.confirmed else ()),
    ]
    found = next((one for one in held if one.id == requirement_id), None)
    if found is None or not isinstance(found.target, Unchecked):
        return (
            f"requirement {requirement_id!r} is not an unchecked requirement of brief {brief_id}: "
            "propose the requirement as unchecked first, and write a check only for a "
            "requirement no team check decides"
        )
    source, words = quoted(state.brief.text, found.origin)
    return WrittenFor(found, source, words)


def form(draft: CheckDraft) -> Shaped | str:
    """G1. The formula parses, every name it reads is bound once, every binding is one the
    server can read, and the check reads at least one value from a source, the tables or
    research, so a bare geometry measure is not a check."""
    formula = parse(draft.formula)
    if isinstance(formula, str):
        return formula
    bound: list[Bound] = []
    for name, raw in draft.inputs.items():
        binding = parse_binding(raw)
        if isinstance(binding, str):
            return binding
        bound.append(Bound(name=name, binding=binding))
    shaped = Shaped(formula, tuple(bound))
    return (
        _names_agree(draft, formula)
        or _bindings_exist(draft, shaped)
        or _reads_a_trusted_value(draft, shaped)
        or _units_listed(draft)
        or shaped
    )


def units(draft: CheckDraft, shaped: Shaped) -> str | None:
    """G2. Every sum, min and max holds one dimension, and the formula's value is in the
    limit's dimension, as are the example's result and a limit read from the source."""
    dimensions: dict[str, Dimension] = {}
    for one in shaped.bound:
        own = _dimension_of_input(draft, one)
        if isinstance(own, str):
            return own
        dimensions[one.name] = own
    found = dimension(shaped.formula, dimensions)
    if isinstance(found, str):
        return found
    wanted = dimension_of(UNITS[draft.limit.unit])
    if found != wanted:
        return f"the formula gives {found or 'a number'}, but the limit is in {draft.limit.unit}"
    if dimension_of(UNITS[draft.example.result.unit]) != wanted:
        result = draft.example.result.unit
        return f"the example's result is in {result}, not a unit of {draft.limit.unit}"
    if draft.limit.source is not None:
        unit = next(one.unit for one in draft.sources if one.name == draft.limit.source)
        if dimension_of(UNITS[unit]) != wanted:
            return f"the limit's source value is in {unit}, not a unit of {draft.limit.unit}"
    return None


def _dimension_of_input(draft: CheckDraft, one: Bound) -> Dimension | str:
    binding = one.binding
    if isinstance(binding, SourceInput):
        return dimension_of(UNITS[next(s.unit for s in draft.sources if s.name == binding.name)])
    given = dimension_of(UNITS[draft.example.inputs[one.name].unit])
    match binding:
        case GeometryInput():
            return given
        case TeamInput():
            unit = BINDABLE[(binding.check_id, binding.measure)].unit
        case MaterialInput():
            unit = FIELDS[binding.field].canonical_unit
    if dimension_of(unit) != given:
        shown = draft.example.inputs[one.name].unit
        return f"the example gives {one.name} in {shown}, but {one.name} is in {unit}"
    return given


def _names_agree(draft: CheckDraft, formula: Formula) -> str | None:
    unbound = sorted(formula.names - set(draft.inputs))
    if unbound:
        return f"the formula reads {', '.join(unbound)}, which inputs does not bind"
    unread = sorted(set(draft.inputs) - formula.names)
    if unread:
        return f"inputs binds {', '.join(unread)}, which the formula never reads"
    return None


def _bindings_exist(draft: CheckDraft, shaped: Shaped) -> str | None:
    sources = [one.name for one in draft.sources]
    if len(set(sources)) != len(sources):
        return "two sources share a name"
    geometry = False
    read_sources: set[str] = set()
    for one in shaped.bound:
        binding = one.binding
        match binding:
            case TeamInput() if (binding.check_id, binding.measure) not in BINDABLE:
                offered = ", ".join(f"team:{check}:{measure}" for check, measure in BINDABLE)
                return f"{one.name} binds no team measure: the measures are {offered}"
            case GeometryInput():
                geometry = True
            case SourceInput() if binding.name not in sources:
                return f"{one.name} binds source {binding.name}, which sources does not hold"
            case SourceInput():
                read_sources.add(binding.name)
            case TeamInput() | MaterialInput():
                pass
    if geometry != (draft.geometry is not None):
        return "geometry code is passed exactly when an input binds geometry:<name>"
    if draft.probe is not None and draft.geometry is None:
        return "a probe shape is only for geometry code"
    if draft.limit.source is not None and draft.limit.source not in sources:
        return f"the limit reads source {draft.limit.source}, which sources does not hold"
    unused = sorted(set(sources) - read_sources - {draft.limit.source})
    if unused:
        return f"sources holds {', '.join(unused)}, which neither the formula nor the limit reads"
    wanted = {one.name for one in shaped.bound if not isinstance(one.binding, SourceInput)}
    if set(draft.example.inputs) != wanted:
        names = ", ".join(sorted(wanted)) or "no name"
        return f"the example must give a value for each input not bound to a source: {names}"
    return None


def _reads_a_trusted_value(draft: CheckDraft, shaped: Shaped) -> str | None:
    trusted = [one for one in shaped.bound if isinstance(one.binding, SourceInput | MaterialInput)]
    if trusted or draft.limit.source is not None:
        return None
    return (
        "the formula and its limit read nothing from a source, the materials table or research: "
        "a bare geometry or team measure is not an agent-written check. Bind a constant the "
        "source writes with source:<name>, or a material value with material:<field>"
    )


def _units_listed(draft: CheckDraft) -> str | None:
    used: Mapping[str, str] = {
        "the limit": draft.limit.unit,
        "the example's result": draft.example.result.unit,
        **{f"example input {name}": one.unit for name, one in draft.example.inputs.items()},
        **{f"source {one.name}": one.unit for one in draft.sources},
    }
    for where, unit in used.items():
        if unit not in UNITS:
            return f"{where} is in {unit!r}, not one of {', '.join(UNITS)}"
    return None
