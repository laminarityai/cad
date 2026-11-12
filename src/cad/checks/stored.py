"""Read-only questions about the job results already stored for a variant. `job_store` writes
them and owns the format. Nothing here changes a result, so the job queue is unaffected."""

from pathlib import Path

from cad.checks.job_store import JOBS
from cad.checks.jobs import JobResult
from cad.records import key


def has_result(root: Path, variant_id: str, check_id: str) -> bool:
    """True when a signed job result of this variant holds a result of `check_id`, whatever its
    verdict. A file this store did not sign, or cannot read, is not a result."""
    directory = root / variant_id / JOBS
    try:
        found = sorted(directory.glob("*.signed"))
    except OSError:
        return False
    return any(_holds(root, variant_id, path, check_id) for path in found)


def _holds(root: Path, variant_id: str, path: Path, check_id: str) -> bool:
    try:
        mac, newline, record = path.read_bytes().partition(b"\n")
    except OSError:
        return False
    if not newline or not key.verify(root, f"{variant_id}\0{path.stem}", record, mac):
        return False
    try:
        result = JobResult.model_validate_json(record)
    except ValueError:
        return False
    return any(one.check_id == check_id for one in result.results)
