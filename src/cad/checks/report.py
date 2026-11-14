import hashlib
import math
from base64 import b64decode
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final

from pydantic import TypeAdapter, ValidationError

from cad.checks.container.check import Budget, CheckModule, Quick
from cad.checks.container.inputs import Input
from cad.checks.container.suite import CHECKS, with_requirements
from cad.checks.container.wire import (
    BodyWire,
    CheckedReport,
    FacesWire,
    LoadCaseWire,
    RequestWire,
    ResultWire,
    SourceLiteral,
    StepWire,
    ValueWire,
)
from cad.checks.result import (
    CheckResult,
    Faces,
    Materials,
    Measure,
    Read,
    StepMissing,
    Verdict,
    Where,
)
from cad.checks.values import ReadKey, TableRead, reads_from, values_of
from cad.sandbox import container
from cad.sandbox.bodies import Bodies
from cad.sandbox.container import Job, Ran, TooMuchOutput
from cad.sandbox.image import ANALYSIS, image_tag
from cad.sandbox.stage import CONTAINER_ENTRY, PACKAGE_PATH, Sources, read_sources
from cad.tables.materials import UNITS, MaterialsTable, Source

REASON_CAP = 1024
SCORER: Final = "cad.scorecard.score"

# NaN passes `strict=True`, so `parse` checks `math.isfinite` itself.
REPORT: Final = TypeAdapter(CheckedReport)
STEP: Final = TypeAdapter(StepWire)


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
class Request:
    wire: RequestWire
    material: Materials
    reads: Mapping[ReadKey, TableRead]
    table_version: str
    bodies: Bodies = ()


def build_request(
    material: Materials,
    table: MaterialsTable,
    checks: Sequence[CheckSpec] = QUICK,
    load_cases: Sequence[LoadCaseWire] = (),
    *,
    bodies: Bodies = (),
    context_bytes: int = 0,
) -> Request:
    """Raises ValueError when `material` is not one key for a variant of no named body, or one
    key for each of `bodies` in order."""
    ids = [spec.id for spec in checks]
    taken = sorted(set[Input]().union(*(spec.takes for spec in closure(ids))))
    if isinstance(material, str):
        if bodies:
            raise ValueError("a variant of named bodies is scored with a material for each body")
        values, reads = values_of(material, table, taken, "")
        wire = _wire(ids, values, load_cases, context_bytes, [])
        return Request(wire, material, reads, table.version)
    if [one.body for one in material] != [body.name for body in bodies]:
        raise ValueError("the materials do not name the variant's bodies in order")
    each: list[BodyWire] = []
    reads: dict[ReadKey, TableRead] = {}
    for body, made in zip(bodies, material, strict=True):
        values, read = values_of(made.key, table, taken, body.name)
        each.append({"name": body.name, "solids": list(body.solids), "values": values})
        reads |= read
    wire = _wire(ids, {}, load_cases, context_bytes, each)
    return Request(wire, material, reads, table.version, bodies)


def reads_of(spec: CheckSpec, request: Request) -> tuple[Read, ...]:
    """What each value `spec` takes was read from, body by body on a variant of named bodies."""
    if not request.bodies:
        return reads_from(spec.takes, request.reads, request.wire["values"], "")
    wanted = resting_on(request)
    return tuple(
        read
        for body in request.wire["bodies"]
        if body["name"] in wanted
        for read in reads_from(spec.takes, request.reads, body["values"], body["name"])
    )


def resting_on(request: Request) -> tuple[str, ...]:
    """The bodies whose values a result rests on, "" for a variant of no named body. A load case
    is solved on the one body it names alone, so it rests on that body, and on none when it names
    no body."""
    names = tuple(body.name for body in request.bodies)
    if not names:
        return ("",)
    cases = request.wire["load_cases"]
    if not cases:
        return names
    solved = {case.get("body") for case in cases}
    return tuple(name for name in names if name in solved)


def _wire(
    ids: list[str],
    values: dict[str, ValueWire],
    load_cases: Sequence[LoadCaseWire],
    context_bytes: int,
    bodies: list[BodyWire],
) -> RequestWire:
    return {
        "checks": ids,
        "values": values,
        "load_cases": list(load_cases),
        "context_bytes": context_bytes,
        "bodies": bodies,
    }


@dataclass(frozen=True, slots=True)
class Parsed:
    results: tuple[CheckResult, ...]
    step: bytes | StepMissing
    timed_out: bool = False


def parse(ran: Ran, request: Request, job: Job) -> Parsed:
    """The container sends the results as one line and then the STEP as another. Results whose
    line is whole stand even when the container dies after it, as while it writes the STEP."""
    parsed = _read(ran, request, job, closure(request.wire["checks"]))
    return replace(parsed, timed_out=ran.attended.killed_at_deadline)


def _read(ran: Ran, request: Request, job: Job, expected: Sequence[CheckSpec]) -> Parsed:
    seen, state = ran.attended, ran.state
    if isinstance(seen.report, TooMuchOutput):
        if state.OOMKilled:
            return _refused(_out_of_memory(job), expected)
        cap = container.REPORT_CAP // 2**20
        return _refused(f"the check container sent more than {cap} MiB", expected)
    line, newline, rest = seen.report.partition(b"\n")
    stopped = _stopped(ran, job)
    if stopped is not None and not newline:
        return _refused(f"{stopped} before it sent a report", expected)
    if not seen.report:
        return _refused("the check container sent no report", expected)
    try:
        report = REPORT.validate_json(line, strict=True)
        step: StepWire = (
            {"kind": "missing", "reason": f"{stopped} while it wrote the STEP"}
            if stopped is not None
            else STEP.validate_json(rest, strict=True)
        )
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        reason = f"the check container sent a malformed report: {where}: {first['msg']}"
        return _refused(reason, expected)
    return _accepted(report, step, request, expected)


def _stopped(ran: Ran, job: Job) -> str | None:
    """Why the container stopped before it finished, or None when it exited on its own."""
    state = ran.state
    if ran.attended.killed_at_deadline:
        return f"the check container ran past {job.wall_seconds} s and was killed"
    if state.OOMKilled and state.ExitCode != 0:
        return _out_of_memory(job)
    if state.ExitCode != 0:
        return f"the check container exited with code {state.ExitCode}"
    return None


def _out_of_memory(job: Job) -> str:
    return f"the check container ran out of memory ({job.memory_mb} MB)"


def _accepted(
    report: CheckedReport, step: StepWire, request: Request, expected: Sequence[CheckSpec]
) -> Parsed:
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
            body = measured["name"].partition(":")[2] if request.bodies else ""
            sent = request.reads.get((read, body))
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
        dict.fromkeys(
            request.reads[key].source
            for body in resting_on(request)
            for read in dict.fromkeys(spec.reads.values())
            if (key := (read, body)) in request.reads
        )
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


def _refused(reason: str, expected: Sequence[CheckSpec]) -> Parsed:
    return Parsed(unknown_for_all(reason, expected), StepMissing(reason=reason))


def _one_line(text: str) -> str:
    return " ".join(text.split())[:REASON_CAP]


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
