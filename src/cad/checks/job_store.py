import os
import secrets
from pathlib import Path
from typing import Final

from cad.checks.jobs import JobResult, JobSpec
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants import key

JOBS: Final = "jobs"
ATTEMPT_CAP: Final = 2


def result_path(job: JobSpec) -> Path:
    return _directory(job) / f"{job.key}.signed"


def read(job: JobSpec) -> JobResult | None:
    try:
        mac, newline, record = result_path(job).read_bytes().partition(b"\n")
    except OSError:
        return None
    if not newline or not key.verify(job.root, _slot(job), record, mac):
        return None
    try:
        return JobResult.model_validate_json(record)
    except ValueError:
        return None


def write(job: JobSpec, result: JobResult) -> None:
    record = result.model_dump_json().encode()
    data = key.sign(job.root, _slot(job), record) + b"\n" + record
    _replace(job, result_path(job), data, "result")


def interrupted_runs(job: JobSpec) -> int:
    try:
        return int(_attempt_path(job).read_text())
    except (OSError, ValueError):
        return 0


def begin_attempt(job: JobSpec) -> None:
    _replace(job, _attempt_path(job), str(interrupted_runs(job) + 1).encode(), "attempt count")


def end_attempt(job: JobSpec) -> None:
    _attempt_path(job).unlink(missing_ok=True)


def _replace(job: JobSpec, path: Path, data: bytes, what: str) -> None:
    temporary = path.with_name(f".{path.name}-{secrets.token_hex(8)}")
    try:
        path.parent.mkdir(exist_ok=True)
        temporary.write_bytes(data)
        os.replace(temporary, path)
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot store the {what} of a job for variant {job.variant_id}", error, path
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


def _attempt_path(job: JobSpec) -> Path:
    return _directory(job) / f"{job.key}.attempt"


def _directory(job: JobSpec) -> Path:
    return job.root / job.variant_id / JOBS


def _slot(job: JobSpec) -> str:
    return f"{job.variant_id}\0{job.key}"
