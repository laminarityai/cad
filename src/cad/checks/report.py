import hashlib
import math
from base64 import b64decode
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from cad.checks.container.check import Budget, CheckModule, Quick
from cad.checks.container.inputs import WIRE_UNITS, Input
from cad.checks.container.suite import CHECKS, with_requirements
from cad.checks.container.wire import (
    CheckedReport,
    FacesWire,
    LoadCaseWire,
    RequestWire,
    ResultWire,
    SourceLiteral,
    ValueWire,
)
from cad.checks.result import (
    CheckResult,
    Faces,
    Measure,
    Read,
    ReadCited,
    ReadMissing,
    ReadResearched,
    StepMissing,
    Verdict,
    Where,
)
from cad.sandbox import container
from cad.sandbox.container import Job, Ran, TooMuchOutput
from cad.sandbox.image import ANALYSIS, image_tag
from cad.sandbox.stage import CONTAINER_ENTRY, PACKAGE_PATH, Sources, read_sources
from cad.tables.materials import (
    PROJECT_PREFIX,
    UNITS,
    Basis,
    FromResearch,
    FromTable,
    Known,
    Material,
    MaterialsTable,
    Source,
    UnknownMaterial,
)

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
    takes: frozenset[Input]
    reads: Mapping[str, Input]
    budget: Budget
    error_bounds: Mapping[str, float]
    version: str


def check_version(check: CheckModule, sources: Sources, analysis_tag: str) -> str:
    checks = {_path(module.ID) for module in CHECKS}
    shared = (path for path in sorted(sources.files) if path not in checks)
    digest = hashlib.sha256(f"{analysis_tag}\0".encode())
    for path in (*_run_by(check), *shared):
        digest.update(f"{path}\0".encode())
        digest.update(hashlib.sha256(sources.files[path]).digest())
    for name, version in sources.packages.items():
        digest.update(f"{name}=={version}\0".encode())
    return digest.hexdigest()


def _run_by(check: CheckModule) -> tuple[str, ...]:
    return (_path(check.ID), *(path for required in check.REQUIRES for path in _run_by(required)))


def specs(
    sources: Sources, analysis_tag: str, checks: Sequence[CheckModule] = CHECKS
) -> tuple[CheckSpec, ...]:
    for module in checks:
        if not module.SOURCES:
            raise ValueError(f"check {module.ID} cites no source")
        if not set(module.READS) <= set(module.MEASURES):
            raise ValueError(f"check {module.ID} reads a measure it does not declare")
        if not set(module.READS.values()) <= module.TAKES:
            raise ValueError(f"check {module.ID} reads an input it does not take")
    return tuple(
        CheckSpec(
            id=module.ID,
            formula=module.FORMULA,
            sources=tuple(_source(literal) for literal in module.SOURCES),
            measures=module.MEASURES,
            takes=module.TAKES,
            reads=module.READS,
            budget=module.BUDGET,
            error_bounds=module.ERROR_BOUNDS,
            version=check_version(module, sources, analysis_tag),
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
IMAGE_TAG: Final = image_tag(ANALYSIS)
SPECS: Final = specs(DEPENDENCIES, IMAGE_TAG)
QUICK: Final = tuple(spec for spec in SPECS if isinstance(spec.budget, Quick))


def closure(check_ids: Sequence[str]) -> tuple[CheckSpec, ...]:
    wanted = {check.ID for check in with_requirements(check_ids)}
    return tuple(spec for spec in SPECS if spec.id in wanted)


@dataclass(frozen=True, slots=True)
class TableRead:
    magnitude: float
    source: Source
    basis: Basis


@dataclass(frozen=True, slots=True)
class Request:
    wire: RequestWire
    material_key: str
    reads: Mapping[Input, TableRead]
    table_version: str


def build_request(
    material_key: str,
    table: MaterialsTable,
    checks: Sequence[CheckSpec] = QUICK,
    load_cases: Sequence[LoadCaseWire] = (),
    *,
    context_bytes: int = 0,
) -> Request:
    ids = [spec.id for spec in checks]
    taken = sorted(set[Input]().union(*(spec.takes for spec in closure(ids))))
    try:
        material = table.get_material(material_key)
    except UnknownMaterial as error:
        missing: ValueWire = {"kind": "unknown", "reason": str(error)}
        wire = _wire(ids, dict.fromkeys(taken, missing), load_cases, context_bytes)
        return Request(wire, material_key, {}, table.version)
    reads = {wanted: read for wanted in taken if (read := _read(material, wanted)) is not None}
    values: dict[str, ValueWire] = {
        wanted: _value(material, wanted, reads.get(wanted)) for wanted in taken
    }
    wire = _wire(ids, values, load_cases, context_bytes)
    return Request(wire, material_key, reads, table.version)


def _read(material: Material, wanted: Input) -> TableRead | None:
    known = material.value(wanted)
    if not isinstance(known, Known):
        return None
    magnitude = known.magnitude_in(WIRE_UNITS[wanted])
    return TableRead(magnitude, known.source, known.basis)


def _value(material: Material, wanted: Input, read: TableRead | None) -> ValueWire:
    if read is None and material.key.startswith(PROJECT_PREFIX):
        reason = f"{material.key} has no row in the materials table, and no {wanted} is researched"
        return {"kind": "unknown", "reason": reason}
    if read is None:
        reason = f"the materials table has no {wanted} for {material.key}: it says unknown"
        return {"kind": "unknown", "reason": reason}
    return {"kind": "known", "magnitude": read.magnitude}


def reads_of(spec: CheckSpec, request: Request) -> tuple[Read, ...]:
    reads: list[Read] = []
    for wanted in sorted(spec.takes):
        read = request.reads.get(wanted)
        value = request.wire["values"].get(wanted)
        if read is not None:
            match read.basis:
                case FromResearch(sha256=sha256):
                    source = read.source
                    reads.append(
                        ReadResearched(
                            field=wanted, url=source.url, quote=source.quote, sha256=sha256
                        )
                    )
                case FromTable(specimen=specimen):
                    reads.append(ReadCited(field=wanted, specimen=specimen))
        elif value is not None and value["kind"] == "unknown":
            reads.append(ReadMissing(field=wanted, reason=value["reason"]))
    return tuple(reads)


def _wire(
    ids: list[str],
    values: dict[str, ValueWire],
    load_cases: Sequence[LoadCaseWire],
    context_bytes: int,
) -> RequestWire:
    return {
        "checks": ids,
        "values": values,
        "load_cases": list(load_cases),
        "context_bytes": context_bytes,
    }


@dataclass(frozen=True, slots=True)
class Parsed:
    results: tuple[CheckResult, ...]
    step: bytes | StepMissing
    timed_out: bool = False


def parse(ran: Ran, request: Request, job: Job) -> Parsed:
    expected = closure(request.wire["checks"])
    seen, state = ran.attended, ran.state
    if seen.killed_at_deadline:
        reason = f"the check container ran past {job.wall_seconds} s and was killed"
        return Parsed(unknown_for_all(reason, expected), StepMissing(reason=reason), timed_out=True)
    if state.OOMKilled and (isinstance(seen.report, TooMuchOutput) or state.ExitCode != 0):
        return _refused(f"the check container ran out of memory ({job.memory_mb} MB)", expected)
    if isinstance(seen.report, TooMuchOutput):
        cap = container.REPORT_CAP // 2**20
        return _refused(f"the check container sent more than {cap} MiB", expected)
    if state.ExitCode != 0:
        code = state.ExitCode
        return _refused(
            f"the check container exited with code {code} before it sent a report", expected
        )
    if not seen.report:
        return _refused("the check container sent no report", expected)
    try:
        report = REPORT.validate_json(seen.report, strict=True)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        return _refused(
            f"the check container sent a malformed report: {where}: {first['msg']}", expected
        )
    return _accepted(report, request, expected)


def _accepted(report: CheckedReport, request: Request, expected: Sequence[CheckSpec]) -> Parsed:
    wire_ids = [result["id"] for result in report["results"]]
    if wire_ids != [spec.id for spec in expected]:
        return _refused(
            f"the check container reported {wire_ids}, not the checks it was given", expected
        )
    results: list[CheckResult] = []
    for spec, wire in zip(expected, report["results"], strict=True):
        problem = _problem(spec, wire, request)
        if problem is not None:
            return _refused(f"{spec.id}: {problem}", expected)
        results.append(_result(spec, wire, request))
    step = report["step"]
    if step["kind"] == "missing":
        return Parsed(tuple(results), StepMissing(reason=_one_line(step["reason"])))
    try:
        return Parsed(tuple(results), b64decode(step["base64"], validate=True))
    except ValueError:
        return _refused("the check container sent a STEP that is not base64", expected)


def _problem(spec: CheckSpec, wire: ResultWire, request: Request) -> str | None:
    for measured in wire["measured"]:
        name = measured["name"].split(":", 1)[0]
        if name not in spec.measures:
            return f"measured {measured['name']!r}, which the check does not declare"
        if measured["unit"] != spec.measures[name]:
            return f"{measured['name']} is in {measured['unit']!r}, not {spec.measures[name]!r}"
        if not math.isfinite(measured["magnitude"]):
            return f"{measured['name']} is not a finite number"
        read = spec.reads.get(name)
        if read is not None:
            sent = request.reads.get(read)
            if sent is None:
                return f"{measured['name']} reads {read}, which the host sent no value for"
            if not math.isclose(measured["magnitude"], sent.magnitude, rel_tol=1e-9):
                return (
                    f"{measured['name']} is {measured['magnitude']:g}, "
                    f"but the host sent {sent.magnitude:g}"
                )
    found = wire.get("where")
    if found is None:
        return None
    named = (found, *([found["displacement"]] if "displacement" in found else []))
    if min((i for one in named for i in (*one["support"], *one["load"])), default=0) < 0:
        return "named a face with a negative index"
    return None


def _result(spec: CheckSpec, wire: ResultWire, request: Request) -> CheckResult:
    rows = tuple(
        request.reads[read].source
        for read in dict.fromkeys(spec.reads.values())
        if read in request.reads
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
        reads=reads_of(spec, request),
        where=_where(wire),
    )


def _where(wire: ResultWire) -> Where | None:
    found = wire.get("where")
    if found is None:
        return None
    bending = found.get("displacement")
    return Where(
        support=tuple(found["support"]),
        load=tuple(found["load"]),
        displacement=None if bending is None else _faces(bending),
    )


def _faces(wire: FacesWire) -> Faces:
    return Faces(support=tuple(wire["support"]), load=tuple(wire["load"]))


def _one_line(text: str) -> str:
    return " ".join(text.split())[:REASON_CAP]


def _refused(reason: str, expected: Sequence[CheckSpec]) -> Parsed:
    return Parsed(unknown_for_all(reason, expected), StepMissing(reason=reason))


def unknown_for_all(reason: str, checks: Sequence[CheckSpec] = QUICK) -> tuple[CheckResult, ...]:
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
        for spec in checks
    )
