"""Place a `Measure` of a check result: computed by a registered check at its current version, and
read from the materials table by exact key when the check declares the read in `READS`. Place a
face index of its `where` the same way: the check found the face, and the agent never names one
(ADR-0007).

A result is a `CheckResult`, or a `MeasureOnly`: the same stored result, reported with no verdict
because only a load nobody confirmed reads it. Both carry the check's measures, version and
sources, so one rule places both.

On a card the session was shown, each measure must also equal the measure of the same name in
the signed job result the card's own variant, material, table version and instance key
(`signedjobs.py`), and each face index the index at the same place in that result's `where`. A
result's verdict and its other fields are compared there.
"""

import math
from collections.abc import Mapping

import pint
from cardnumbers import Where, numbers_in, path_of
from chain import (
    CheckStep,
    Outcome,
    ResearchedStep,
    Resolved,
    Stale,
    Step,
    TableStep,
    Unresolved,
)
from signedjobs import SignedJobs

from cad.checks.report import CheckSpec
from cad.checks.result import CheckResult, Measure
from cad.scorecard.model import Scorecard
from cad.scorecard.unjudged import MeasureOnly
from cad.tables.materials import (
    UNITS,
    FromResearch,
    Known,
    MaterialsTable,
    UnknownMaterial,
    magnitude,
)

REL_TOL = 1e-9

type Measuring = CheckResult | MeasureOnly


def same(held: pint.Quantity, expected: pint.Quantity) -> bool:
    unit = str(expected.units)
    try:
        value = magnitude(held, unit)
    except pint.DimensionalityError:
        return False
    return math.isclose(value, magnitude(expected, unit), rel_tol=REL_TOL)


def trace_measure(
    card: Scorecard,
    result: Measuring,
    measure: Measure,
    table: MaterialsTable,
    specs: Mapping[str, CheckSpec],
    signed: SignedJobs | None,
) -> Outcome:
    """`signed` is None for a card that is not bound to its jobs: the server's own reading, or a
    transcript traced alone."""
    spec = specs.get(result.check_id)
    if spec is None:
        return Unresolved(f"no check called {result.check_id!r} is registered")
    base = measure.name.split(":", 1)[0]
    unit = spec.measures.get(base)
    if unit is None:
        return Unresolved(f"{spec.id} does not declare a measure called {base!r}")
    if measure.value.units != UNITS.Unit(unit):
        return Unresolved(f"{measure.name} is in {measure.value.units:~P}, not {unit}")
    if result.version != spec.version:
        return Stale(
            f"{spec.id} version {result.version[:12]} is not the current {spec.version[:12]}"
        )
    if signed is not None:
        unsigned = _unsigned(measure, signed.result(result.check_id, result.instance))
        if unsigned is not None:
            return unsigned
    steps: list[Step] = [CheckStep(spec.id, spec.version)]
    field = spec.reads.get(base)
    if field is not None:
        read = _table_step(card, result, measure, field, unit, table)
        if not isinstance(read, TableStep | ResearchedStep):
            return read
        steps.append(read)
    return Resolved(tuple(steps))


def trace_face(
    result: Measuring,
    at: Where,
    value: str,
    specs: Mapping[str, CheckSpec],
    signed: SignedJobs | None,
) -> Outcome:
    """`at` is where the face index `value` sits in the result's `where`."""
    spec = specs.get(result.check_id)
    if spec is None:
        return Unresolved(f"no check called {result.check_id!r} is registered")
    if result.version != spec.version:
        return Stale(
            f"{spec.id} version {result.version[:12]} is not the current {spec.version[:12]}"
        )
    if signed is not None:
        held = signed.result(result.check_id, result.instance)
        if isinstance(held, Unresolved):
            return held
        faces = (
            {}
            if held.where is None
            else {one.where: one.value for one in numbers_in(held.where.model_dump(mode="json"))}
        )
        if faces.get(at) != value:
            return Unresolved(
                f"face {path_of(at)} is {value} on the card, but the signed job result holds "
                f"{faces.get(at, 'none there')}"
            )
    return Resolved((CheckStep(spec.id, spec.version),))


def _unsigned(measure: Measure, held: CheckResult | Unresolved) -> Unresolved | None:
    if isinstance(held, Unresolved):
        return held
    found = next((one for one in held.measured if one.name == measure.name), None)
    if found is None:
        return Unresolved(
            f"{measure.name} is {measure.value:g~P} on the card, but the signed job result "
            f"holds no {measure.name}"
        )
    if not same(measure.value, found.value):
        return Unresolved(
            f"{measure.name} is {measure.value:g~P} on the card, but the signed job result "
            f"holds {found.value:g~P}"
        )
    return None


def _table_step(
    card: Scorecard,
    result: Measuring,
    measure: Measure,
    field: str,
    unit: str,
    table: MaterialsTable,
) -> TableStep | ResearchedStep | Stale | Unresolved:
    if card.table_version != table.version:
        return Stale(
            f"scored against materials table {_short(card.table_version)}, "
            f"not the current {_short(table.version)}"
        )
    try:
        material = table.get_material(card.material_key)
    except UnknownMaterial:
        return Unresolved(f"the materials table has no row {card.material_key!r}")
    cited = material.value(field)
    if not isinstance(cited, Known):
        return Unresolved(f"{card.material_key} has no cited {field}: the table says unknown")
    if not math.isclose(measure.value.m_as(unit), cited.magnitude_in(unit), rel_tol=REL_TOL):  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        return Unresolved(
            f"{measure.name} is {measure.value:g~P}, but {card.material_key} {field} "
            f"is {cited.quantity:g~P}"
        )
    if cited.source not in result.sources:
        return Unresolved(f"the {result.check_id} result does not carry the {field} source")
    if isinstance(cited.basis, FromResearch):
        return ResearchedStep(card.material_key, field, cited.source, cited.basis.record)
    return TableStep(card.material_key, field, cited.source)


def _short(version: str) -> str:
    head, plus, research = version.partition("+")
    return head[:12] + plus + research
