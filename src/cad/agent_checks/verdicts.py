"""The verdict of an agent-written check the person approved, on one scored variant (ADR-0011).

The geometry code runs in the sandbox, plain and turned, and the values both runs agree on are
kept in `runs`. The formula is evaluated here, on the host, from those values, the team results
on the card, the material row and the values the record's pages give. The result is compared
with the limit the person confirmed. The row it gives is labelled and counted apart from what
reviewed checks decide.
"""

import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pint

from cad.agent_checks import formula, harness, runs, turned
from cad.agent_checks.example import quantity
from cad.agent_checks.model import (
    UNITS,
    Bound,
    GeometryInput,
    MaterialInput,
    NamedValue,
    SourceInput,
    TeamInput,
)
from cad.agent_checks.runs import GeometryRun
from cad.agent_checks.store import StoredCheck
from cad.briefs.model import AgentLimit, Requirement
from cad.checks.result import CheckResult, Comparator, Verdict
from cad.projects.model import ProjectId
from cad.sandbox import image
from cad.sandbox.host import SandboxUnavailable
from cad.scorecard.model import AgainstBrief, AgentChecked, AgentCheckValue, Unverified
from cad.scorecard.unjudged import Reported
from cad.tables.materials import UNITS as PINT
from cad.tables.materials import FromResearch, Known, Material

NOISE: Final = 1e-9
NOT_RUN: Final = (
    "score_variant has not run this check's code on this part yet; score the variant again"
)
PASSED: Final = "The agent-written check's value meets the limit you confirmed."
MISSED: Final = "The agent-written check's value does not meet the limit you confirmed."
_CODE: Final = (harness.__file__, turned.__file__, formula.__file__)

type Results = Sequence[Reported]


@dataclass(frozen=True, slots=True)
class Approved:
    """A confirmed requirement held to an agent-written check the person approved."""

    requirement: Requirement
    target: AgentLimit
    stored: StoredCheck


def version(stored: StoredCheck) -> str:
    """Changes when the record, the code that runs it or the sandbox image changes."""
    digest = hashlib.sha256(f"{stored.sha256}\0{image.image_tag(image.BUILD)}\0".encode())
    digest.update(f"{formula.EVALUATOR}\0".encode())
    for path in _CODE:
        digest.update(hashlib.sha256(Path(path).read_bytes()).digest())
    return digest.hexdigest()


def run_geometry(
    projects: Path, project: ProjectId, brep: bytes, brep_sha256: str, checks: Sequence[StoredCheck]
) -> None:
    """Run the geometry code of each check not yet run on this shape, and keep what it gave. A
    sandbox that is down keeps nothing, so the next score runs it."""
    wanted = [
        one
        for one in checks
        if one.check.geometry is not None
        and runs.read(projects, project, version(one), brep_sha256) is None
    ]
    if not wanted:
        return
    try:
        measured = turned.on_variant(brep, [one.check for one in wanted])
    except SandboxUnavailable:
        return
    for one, found in zip(wanted, measured, strict=True):
        match found:
            case turned.Unmeasured(reason=reason) | turned.Unsound(reason=reason):
                values: tuple[NamedValue, ...] = ()
                why: str | None = (
                    reason
                    if isinstance(found, turned.Unmeasured)
                    else f"its answers cannot be trusted on this part: {reason}"
                )
            case _:
                values = tuple(_named(one, name, value) for name, value in found.items())
                why = None
        run = GeometryRun(
            check_sha256=one.sha256,
            version=version(one),
            brep_sha256=brep_sha256,
            values=values,
            reason=why,
        )
        runs.keep(projects, project, run)


def judged(
    basis: AgainstBrief,
    approved: Sequence[Approved],
    results: Results,
    material: Material,
    geometry: Callable[[StoredCheck], GeometryRun | None],
) -> AgainstBrief:
    """`basis` with each approved check's Unverified row replaced by its labelled verdict."""
    by_id: dict[str, Approved] = {one.requirement.id: one for one in approved}
    rows = tuple(
        _decided(by_id[row.requirement_id], row.statement, results, material, geometry)
        if isinstance(row, Unverified) and row.requirement_id in by_id
        else row
        for row in basis.requirements
    )
    return AgainstBrief.model_validate(
        {
            **dict(basis),
            "requirements": rows,
            "unverified_requirements": tuple(
                one.requirement_id for one in rows if isinstance(one, Unverified)
            ),
            "agent_checked_requirements": tuple(
                one.requirement_id for one in rows if isinstance(one, AgentChecked)
            ),
        }
    )


def _decided(
    one: Approved,
    statement: str,
    results: Results,
    material: Material,
    geometry: Callable[[StoredCheck], GeometryRun | None],
) -> AgentChecked:
    check = one.stored.check
    limit = _limit(one)
    inputs: list[AgentCheckValue] = []
    reason: str | None = None
    run = geometry(one.stored) if check.geometry is not None else None
    for bound in check.inputs:
        found = _input(bound, one.stored, run, results, material)
        if isinstance(found, str):
            reason = reason or found
        else:
            inputs.append(found)
    value = None
    if reason is None:
        found = _value(check.formula, {each.name: each.value for each in inputs})
        if isinstance(found, str):
            reason = found
        else:
            value = _in(found, check.unit)
    verdict = Verdict.UNKNOWN
    if value is not None:
        verdict = Verdict.PASS if _holds(value, limit, one.target.comparator) else Verdict.FAIL
        reason = PASSED if verdict is Verdict.PASS else MISSED
    return AgentChecked(
        requirement_id=one.requirement.id,
        statement=statement,
        check_sha256=one.stored.sha256,
        title=check.title,
        formula=check.formula,
        version=version(one.stored),
        verdict=verdict,
        reason=reason or MISSED,
        value=value,
        comparator=one.target.comparator,
        limit=limit,
        inputs=tuple(inputs),
        pages=tuple(dict.fromkeys(source.cited.url for source in check.sources)),
    )


def _input(
    bound: Bound,
    stored: StoredCheck,
    run: GeometryRun | None,
    results: Results,
    material: Material,
) -> AgentCheckValue | str:
    binding = bound.binding
    match binding:
        case GeometryInput(name=name):
            if run is None:
                return NOT_RUN
            if run.reason is not None:
                return f"the check's code could not measure this part: {run.reason}"
            value = next((quantity(one) for one in run.values if one.name == name), None)
            if value is None:
                return f"the check's code gave no {name} on this part"
            return AgentCheckValue(name=bound.name, read=f"geometry:{name}", value=value)
        case TeamInput(check_id=check_id, measure=measure):
            return _team(bound.name, check_id, measure, results)
        case MaterialInput(field=field):
            held = material.value(field)
            if not isinstance(held, Known):
                return f"the materials table has no {field} for {material.name}"
            researched = ", researched" if isinstance(held.basis, FromResearch) else ""
            read = f"material:{field} of {material.name}{researched}"
            return AgentCheckValue(name=bound.name, read=read, value=held.quantity)
        case SourceInput(name=name):
            source = next(one for one in stored.check.sources if one.name == name)
            read = f"source:{name}, {source.cited.url}"
            return AgentCheckValue(name=bound.name, read=read, value=quantity(source))


def _team(name: str, check_id: str, measure: str, results: Results) -> AgentCheckValue | str:
    result = next((one for one in results if one.check_id == check_id and not one.instance), None)
    if result is None:
        return f"the {check_id} check did not run on this variant"
    if not isinstance(result, CheckResult):
        return f"the {check_id} check has not finished"
    value = next((one.value for one in result.measured if one.name == measure), None)
    if result.verdict is not Verdict.PASS or value is None:
        return f"the {check_id} check gave no {measure}: {result.reason}"
    return AgentCheckValue(name=name, read=f"team:{check_id}:{measure}", value=value)


def _limit(one: Approved) -> pint.Quantity:
    check = one.stored.check
    if one.target.limit is not None:
        return _in(one.target.limit, check.unit)
    source = next(each for each in check.sources if each.name == check.limit_source)
    return _in(quantity(source), check.unit)


def _value(text: str, values: Mapping[str, pint.Quantity]) -> pint.Quantity | str:
    parsed = formula.parse(text)
    if isinstance(parsed, str):
        return f"the formula no longer parses: {parsed}"
    found = formula.evaluate(parsed, values)
    if not isinstance(found, str) and not math.isfinite(_magnitude(found, found)):
        return "the formula's value is not a finite number"
    return found


def _holds(value: pint.Quantity, limit: pint.Quantity, comparator: Comparator) -> bool:
    a, b = _magnitude(value, limit), _magnitude(limit, limit)
    match comparator:
        case Comparator.AT_MOST:
            return a <= b + NOISE * abs(b)
        case Comparator.AT_LEAST:
            return a >= b - NOISE * abs(b)


def _in(value: pint.Quantity, unit: str) -> pint.Quantity:
    return PINT.Quantity(_magnitude(value, PINT.Quantity(1, UNITS[unit])), UNITS[unit])


def _magnitude(value: pint.Quantity, like: pint.Quantity) -> float:
    return float(value.m_as(like.units))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _named(stored: StoredCheck, name: str, value: pint.Quantity) -> NamedValue:
    """The value in the unit the record's worked example gives it."""
    unit = next(one.unit for one in stored.check.example.inputs if one.name == name)
    return NamedValue(name=name, value=_magnitude(value, PINT.Quantity(1, UNITS[unit])), unit=unit)
