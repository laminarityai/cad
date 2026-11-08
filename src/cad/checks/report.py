import hashlib
import math
from base64 import b64decode
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from cad.checks.container.check import CheckModule
from cad.checks.container.inputs import WIRE_UNITS, Input
from cad.checks.container.suite import CHECKS
from cad.checks.container.wire import (
    CheckedReport,
    RequestWire,
    ResultWire,
    SourceLiteral,
    ValueWire,
)
from cad.checks.result import CheckResult, Measure, StepMissing, Verdict
from cad.sandbox import container
from cad.sandbox.container import Job, Ran, TooMuchOutput
from cad.sandbox.image import ANALYSIS, image_tag
from cad.sandbox.stage import CONTAINER_ENTRY, PACKAGE_PATH, Sources, read_sources
from cad.tables.materials import UNITS, Cited, Material, MaterialsTable, Source, UnknownMaterial

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


@dataclass(frozen=True, slots=True)
class TableRead:
    magnitude: float
    source: Source


@dataclass(frozen=True, slots=True)
class Request:
    wire: RequestWire
    material_key: str
    reads: Mapping[Input, TableRead]
    table_version: str


def build_request(material_key: str, table: MaterialsTable) -> Request:
    taken = sorted(set[Input]().union(*(spec.takes for spec in SPECS)))
    try:
        material = table.get_material(material_key)
    except UnknownMaterial as error:
        missing: ValueWire = {"kind": "unknown", "reason": str(error)}
        return Request(_wire(dict.fromkeys(taken, missing)), material_key, {}, table.version)
    reads = {wanted: read for wanted in taken if (read := _read(material, wanted)) is not None}
    values: dict[str, ValueWire] = {
        wanted: _value(material, wanted, reads.get(wanted)) for wanted in taken
    }
    return Request(_wire(values), material_key, reads, table.version)


def _read(material: Material, wanted: Input) -> TableRead | None:
    cited = material.value(wanted)
    if not isinstance(cited, Cited):
        return None
    return TableRead(cited.magnitude_in(WIRE_UNITS[wanted]), cited.source)


def _value(material: Material, wanted: Input, read: TableRead | None) -> ValueWire:
    if read is None:
        reason = f"the materials table has no {wanted} for {material.key}: it says unknown"
        return {"kind": "unknown", "reason": reason}
    return {"kind": "known", "magnitude": read.magnitude}


def _wire(values: dict[str, ValueWire]) -> RequestWire:
    return {"checks": [spec.id for spec in SPECS], "values": values}


@dataclass(frozen=True, slots=True)
class Parsed:
    results: tuple[CheckResult, ...]
    step: bytes | StepMissing
    timed_out: bool = False


def parse(ran: Ran, request: Request, job: Job) -> Parsed:
    seen, state = ran.attended, ran.state
    if seen.killed_at_deadline:
        reason = f"the check container ran past {job.wall_seconds} s and was killed"
        return Parsed(unknown_for_all(reason), StepMissing(reason=reason), timed_out=True)
    if state.OOMKilled and (isinstance(seen.report, TooMuchOutput) or state.ExitCode != 0):
        return _refused(f"the check container ran out of memory ({job.memory_mb} MB)")
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
    )


def _one_line(text: str) -> str:
    return " ".join(text.split())[:REASON_CAP]


def _refused(reason: str) -> Parsed:
    return Parsed(unknown_for_all(reason), StepMissing(reason=reason))


def unknown_for_all(reason: str, checks: Sequence[CheckSpec] = SPECS) -> tuple[CheckResult, ...]:
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
