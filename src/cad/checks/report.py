import hashlib
import math
from base64 import b64decode
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from cad.checks.container.check import CheckModule
from cad.checks.container.suite import CHECKS
from cad.checks.container.wire import CheckedReport, RequestWire, ResultWire, SourceLiteral
from cad.checks.result import CheckResult, Measure, StepMissing, Verdict
from cad.sandbox import container
from cad.sandbox.container import Ran, TooMuchOutput
from cad.sandbox.stage import CONTAINER_ENTRY, PACKAGE_PATH, Sources, read_sources
from cad.tables.materials import UNITS, Cited, MaterialsTable, Source, UnknownMaterial

REASON_CAP = 1024
SCORER: Final = "cad.scorecard.score"

# NaN passes `strict=True`, so `parse` checks `math.isfinite` itself.
REPORT: Final = TypeAdapter(CheckedReport)


@dataclass(frozen=True, slots=True)
class CheckSpec:
    id: str
    formula: str
    sources: tuple[Source, ...]
    measures: Mapping[str, str]
    reads: Mapping[str, str]
    version: str


def check_version(check: CheckModule, sources: Sources) -> str:
    checks = {_path(module.ID) for module in CHECKS}
    shared = (path for path in sorted(sources.files) if path not in checks)
    digest = hashlib.sha256()
    for path in (*_run_by(check), *shared):
        digest.update(f"{path}\0".encode())
        digest.update(hashlib.sha256(sources.files[path]).digest())
    for name, version in sources.packages.items():
        digest.update(f"{name}=={version}\0".encode())
    return digest.hexdigest()


def _run_by(check: CheckModule) -> tuple[str, ...]:
    return (_path(check.ID), *(path for required in check.REQUIRES for path in _run_by(required)))


def specs(sources: Sources, checks: Sequence[CheckModule] = CHECKS) -> tuple[CheckSpec, ...]:
    for module in checks:
        if not module.SOURCES:
            raise ValueError(f"check {module.ID} cites no source")
        if not set(module.READS) <= set(module.MEASURES):
            raise ValueError(f"check {module.ID} reads a measure it does not declare")
    return tuple(
        CheckSpec(
            id=module.ID,
            formula=module.FORMULA,
            sources=tuple(_source(literal) for literal in module.SOURCES),
            measures=module.MEASURES,
            reads=module.READS,
            version=check_version(module, sources),
        )
        for module in checks
    )


def _path(check_id: str) -> str:
    return f"{PACKAGE_PATH}/{check_id}.py"


def _source(literal: SourceLiteral) -> Source:
    return Source(
        url=literal["url"],
        title=literal["title"],
        page=literal["page"],
        retrieved=literal["retrieved"],
        standard=literal["standard"],
        quote=literal["quote"],
    )


DEPENDENCIES: Final = read_sources(CONTAINER_ENTRY, SCORER)
SPECS: Final = specs(DEPENDENCIES)


@dataclass(frozen=True, slots=True)
class TableRead:
    """One number the host sends from a materials table row, in the unit its measure declares."""

    magnitude: float
    source: Source


@dataclass(frozen=True, slots=True)
class Request:
    wire: RequestWire
    material_key: str
    reads: Mapping[str, TableRead]
    table_version: str


def build_request(material_key: str, table: MaterialsTable) -> Request:
    try:
        material = table.get_material(material_key)
    except UnknownMaterial as error:
        return _unknown_density(material_key, table, str(error))
    density = material.density
    if not isinstance(density, Cited):
        reason = f"the materials table has no density for {material_key}: it says unknown"
        return _unknown_density(material_key, table, reason)
    wire: RequestWire = {
        "density": {"kind": "known", "kg_per_mm3": density.magnitude_in("kg/mm^3")}
    }
    sent = TableRead(density.magnitude_in("kg/mm^3"), density.source)
    return Request(wire, material_key, {"density": sent}, table.version)


def _unknown_density(material_key: str, table: MaterialsTable, reason: str) -> Request:
    return Request(
        {"density": {"kind": "unknown", "reason": reason}}, material_key, {}, table.version
    )


@dataclass(frozen=True, slots=True)
class Parsed:
    results: tuple[CheckResult, ...]
    step: bytes | StepMissing


def parse(ran: Ran, request: Request, wall_seconds: int) -> Parsed:
    seen, state = ran.attended, ran.state
    if seen.killed_at_deadline:
        return _refused(f"the check container ran past {wall_seconds} s and was killed")
    if state.OOMKilled and (isinstance(seen.report, TooMuchOutput) or state.ExitCode != 0):
        return _refused(f"the check container ran out of memory ({container.MEMORY_MB} MB)")
    if isinstance(seen.report, TooMuchOutput):
        return _refused(f"the check container sent more than {container.REPORT_CAP // 2**20} MiB")
    if state.ExitCode != 0:
        code = state.ExitCode
        return _refused(f"the check container exited with code {code} before it sent a report")
    if not seen.report:
        return _refused("the check container sent no report")
    try:
        report = REPORT.validate_json(seen.report, strict=True)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        return _refused(f"the check container sent a malformed report: {where}: {first['msg']}")
    return _accepted(report, request)


def _accepted(report: CheckedReport, request: Request) -> Parsed:
    wire_ids = [result["id"] for result in report["results"]]
    if wire_ids != [spec.id for spec in SPECS]:
        return _refused(f"the check container reported {wire_ids}, not the checks it was given")
    results: list[CheckResult] = []
    for spec, wire in zip(SPECS, report["results"], strict=True):
        problem = _problem(spec, wire, request)
        if problem is not None:
            return _refused(f"{spec.id}: {problem}")
        results.append(_result(spec, wire, request))
    step = report["step"]
    if step["kind"] == "missing":
        return Parsed(tuple(results), StepMissing(reason=_one_line(step["reason"])))
    try:
        return Parsed(tuple(results), b64decode(step["base64"], validate=True))
    except ValueError:
        return _refused("the check container sent a STEP that is not base64")


def _problem(spec: CheckSpec, wire: ResultWire, request: Request) -> str | None:
    for measured in wire["measured"]:
        name = measured["name"].split(":", 1)[0]
        if name not in spec.measures:
            return f"measured {measured['name']!r}, which the check does not declare"
        if measured["unit"] != spec.measures[name]:
            return f"{measured['name']} is in {measured['unit']!r}, not {spec.measures[name]!r}"
        if not math.isfinite(measured["magnitude"]):
            return f"{measured['name']} is not a finite number"
        field = spec.reads.get(name)
        if field is not None:
            sent = request.reads.get(field)
            if sent is None:
                return f"{measured['name']} reads {field}, which the host sent no value for"
            if not math.isclose(measured["magnitude"], sent.magnitude, rel_tol=1e-9):
                return (
                    f"{measured['name']} is {measured['magnitude']:g}, "
                    f"but the host sent {sent.magnitude:g}"
                )
    return None


def _result(spec: CheckSpec, wire: ResultWire, request: Request) -> CheckResult:
    rows = tuple(
        request.reads[field].source
        for field in dict.fromkeys(spec.reads.values())
        if field in request.reads
    )
    return CheckResult(
        check_id=spec.id,
        verdict=Verdict(wire["verdict"]),
        measured=tuple(
            Measure(name=one["name"], value=UNITS.Quantity(one["magnitude"], one["unit"]))
            for one in wire["measured"]
        ),
        formula=spec.formula,
        reason=_one_line(wire["reason"]),
        sources=(*spec.sources, *rows),
        version=spec.version,
    )


def _one_line(text: str) -> str:
    return " ".join(text.split())[:REASON_CAP]


def _refused(reason: str) -> Parsed:
    return Parsed(unknown_for_all(reason), StepMissing(reason=reason))


def unknown_for_all(reason: str) -> tuple[CheckResult, ...]:
    return tuple(
        CheckResult(
            check_id=spec.id,
            verdict=Verdict.UNKNOWN,
            measured=(),
            formula=spec.formula,
            reason=reason,
            sources=spec.sources,
            version=spec.version,
        )
        for spec in SPECS
    )
