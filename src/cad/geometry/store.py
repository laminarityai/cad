import re
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter, ValidationError

from cad.data_root import DATA_ROOT
from cad.geometry import job
from cad.geometry.model import Stored
from cad.records import files
from cad.sandbox.outcome import SandboxUnavailable

GEOMETRY_ROOT: Final = DATA_ROOT / "geometry"
SHA256: Final = re.compile(r"[0-9a-f]{64}")
STORED: Final = TypeAdapter[Stored](Stored)


def path(root: Path, brep_sha256: str) -> Path:
    """Content-addressed: one file per BREP under the current tessellator's version, so a new
    tessellator or analysis image tessellates every BREP again."""
    if SHA256.fullmatch(brep_sha256) is None:
        raise ValueError(f"a BREP hash is 64 lowercase hex digits, not {brep_sha256!r}")
    return root / job.VERSION / f"{brep_sha256}.json"


def read(root: Path, brep_sha256: str) -> Stored | None:
    try:
        return STORED.validate_json(path(root, brep_sha256).read_bytes())
    except (OSError, ValidationError):
        return None


def write(root: Path, stored: Stored) -> None:
    target = path(root, stored.brep_sha256)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        files.replace(target, stored.model_dump_json().encode())
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot store the mesh of BREP {stored.brep_sha256}", error, target
        ) from error
