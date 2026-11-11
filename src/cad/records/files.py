import os
import secrets
import stat
from pathlib import Path
from typing import Final

MAX_RECORD_BYTES: Final = 1024 * 1024


def replace(path: Path, data: bytes) -> None:
    """Write data beside path and rename it over path, so a reader sees the old bytes or the
    new ones. The directory must exist; an OSError propagates, and no temporary file is left."""
    temporary = path.with_name(f".{path.name}-{secrets.token_hex(8)}")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_regular(path: Path, limit: int = MAX_RECORD_BYTES) -> bytes | None:
    """The file's bytes, or None when it is missing, a symlink, not a regular file or over limit."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            return None
        data = file.read(limit + 1)
    return None if len(data) > limit else data


def is_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False
