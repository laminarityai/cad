"""Walk every number on a scorecard to where it came from.

A number is one `Measure` on one check result. It resolves when a chain of steps, each holding a
cited `Source`, leads from it to something a person can read:

- a `CheckStep`: the check that measured it, at the version that ran, and the sources that check
  cites. The version and the sources must be the ones the check has today.
- a `TableStep`: when the check read the number from the materials table, the table row, found by
  exact key, with its `Source`. The number must equal the row's value.

A number that breaks any rule is `Unresolved`, with the first rule it broke. The tracer re-runs
nothing, so it shows where a number is from and not that the geometry produced it. `agree.py`
checks that.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from cad.checks.report import CheckSpec
from cad.checks.result import CheckResult, Measure
from cad.scorecard.model import Scorecard
from cad.tables.materials import UNITS, Cited, MaterialsTable, Source, UnknownMaterial

# (check id, measure name) -> the materials table field that the check reads the number from.
TABLE_READS: Final[Mapping[tuple[str, str], str]] = {("mass", "density"): "density"}
TABLE_UNITS: Final[Mapping[str, str]] = {"density": "kg/mm^3"}
REL_TOL: Final = 1e-9


@dataclass(frozen=True, slots=True)
class CheckStep:
    check_id: str
    version: str
    sources: tuple[Source, ...]


@dataclass(frozen=True, slots=True)
class TableStep:
    material_key: str
    field: str
    source: Source


type Step = CheckStep | TableStep


@dataclass(frozen=True, slots=True)
class Resolved:
    steps: tuple[Step, ...]


@dataclass(frozen=True, slots=True)
class Unresolved:
    reason: str


@dataclass(frozen=True, slots=True)
class Traced:
    variant_id: str
    check_id: str
    name: str
    value: str
    outcome: Resolved | Unresolved


def trace_card(
    card: Scorecard, table: MaterialsTable, specs: Mapping[str, CheckSpec]
) -> tuple[Traced, ...]:
    return tuple(
        Traced(
            card.variant_id,
            result.check_id,
            measure.name,
            f"{measure.value:g~P}",
            _trace(card, result, measure, table, specs),
        )
        for result in card.results
        for measure in result.measured
    )


def _trace(
    card: Scorecard,
    result: CheckResult,
    measure: Measure,
    table: MaterialsTable,
    specs: Mapping[str, CheckSpec],
) -> Resolved | Unresolved:
    spec = specs.get(result.check_id)
    if spec is None:
        return Unresolved(f"no check called {result.check_id!r} is registered")
    base = measure.name.split(":", 1)[0]
    unit = spec.measures.get(base)
    if unit is None:
        return Unresolved(f"{spec.id} does not declare a measure called {base!r}")
    if measure.value.units != UNITS.Unit(unit):
        return Unresolved(f"{measure.name} is in {measure.value.units:~P}, not {unit}")
    if not spec.sources:
        return Unresolved(f"{spec.id} cites no source")
    if result.version != spec.version:
        return Unresolved(
            f"{spec.id} version {result.version[:12]} is not the current {spec.version[:12]}"
        )
    missing = [source.title for source in spec.sources if source not in result.sources]
    if missing:
        return Unresolved(f"the {spec.id} result does not carry its cited source: {missing[0]}")
    steps: list[Step] = [CheckStep(spec.id, spec.version, spec.sources)]
    field = TABLE_READS.get((spec.id, base))
    if field is not None:
        read = _table_step(card, result, measure, field, table)
        if isinstance(read, Unresolved):
            return read
        steps.append(read)
    return Resolved(tuple(steps))


def _table_step(
    card: Scorecard, result: CheckResult, measure: Measure, field: str, table: MaterialsTable
) -> TableStep | Unresolved:
    if card.table_version != table.version:
        return Unresolved(
            f"scored against materials table {card.table_version[:12]}, "
            f"not the current {table.version[:12]}"
        )
    try:
        material = table.get_material(card.material_key)
    except UnknownMaterial:
        return Unresolved(f"the materials table has no row {card.material_key!r}")
    cited = getattr(material, field)
    if not isinstance(cited, Cited):
        return Unresolved(f"{card.material_key} has no cited {field}: the table says unknown")
    unit = TABLE_UNITS[field]
    if not math.isclose(measure.value.m_as(unit), cited.magnitude_in(unit), rel_tol=REL_TOL):  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        return Unresolved(
            f"{measure.name} is {measure.value:g~P}, but {card.material_key} {field} "
            f"is {cited.quantity:g~P}"
        )
    if cited.source not in result.sources:
        return Unresolved(f"the {result.check_id} result does not carry the {field} source")
    return TableStep(card.material_key, field, cited.source)
