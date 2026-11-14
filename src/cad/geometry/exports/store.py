from pathlib import Path
from typing import Final

from pydantic import TypeAdapter, ValidationError

from cad.geometry import store
from cad.geometry.exports import job
from cad.geometry.exports.model import ExportFormat, Stored
from cad.records import files
from cad.sandbox.outcome import SandboxUnavailable

EXPORTS: Final = "exports"
MAX_FILE_BYTES: Final = 64 * 1024 * 1024
STORED: Final = TypeAdapter[Stored](Stored)


def path(root: Path, key: str, suffix: str) -> Path:
    """Beside the tessellations in `root`, under the export job's own version. The record is
    written after the three files, so a record means all of them are there."""
    return store.named(root / EXPORTS, job.VERSION, key, suffix)


def read(root: Path, key: str) -> Stored | None:
    record = files.read_regular(path(root, key, "json"))
    try:
        return None if record is None else STORED.validate_json(record)
    except ValidationError:
        return None


def read_file(root: Path, key: str, format: ExportFormat) -> bytes | None:
    return files.read_regular(path(root, key, format), MAX_FILE_BYTES)


def write(root: Path, ran: job.Ran) -> None:
    target = path(root, ran.read.key, "json")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if ran.made is not None:
            files.replace(path(root, ran.read.key, "step"), ran.made.step)
            files.replace(path(root, ran.read.key, "stl"), ran.made.stl)
            files.replace(path(root, ran.read.key, "3mf"), ran.made.threemf)
        files.replace(target, ran.read.model_dump_json().encode())
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot store export {ran.read.key}", error, target
        ) from error
