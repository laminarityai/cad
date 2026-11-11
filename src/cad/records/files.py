import os
import stat
from pathlib import Path
from typing import Final

MAX_RECORD_BYTES: Final = 1024 * 1024


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
