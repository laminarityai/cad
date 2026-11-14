import errno
import logging
import os
import secrets
import stat
from pathlib import Path
from typing import Final

from cad.errors import Unavailable

MAX_RECORD_BYTES: Final = 1024 * 1024
NOT_THERE: Final = frozenset({errno.ENOENT, errno.ENOTDIR, errno.ELOOP})
"""Missing, under a path that is not a directory, or a symlink that `O_NOFOLLOW` refused."""
UNREADABLE: Final = (
    "the server could not read a stored record just now; this is a fault on the server, and "
    "nothing in the project changed: try again"
)
LOG = logging.getLogger(__name__)


class ReadFailed(Unavailable):
    def __init__(self) -> None:
        super().__init__(UNREADABLE)


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
    """The file's bytes, or None when it is missing, a symlink, not a regular file or over limit.
    Any other OSError is a passing fault, not a missing record, so it raises ReadFailed."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        if error.errno in NOT_THERE:
            return None
        raise _failed(path, error) from error
    try:
        with os.fdopen(descriptor, "rb") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                return None
            data = file.read(limit + 1)
    except OSError as error:
        raise _failed(path, error) from error
    return None if len(data) > limit else data


def _failed(path: Path, error: OSError) -> ReadFailed:
    LOG.error("cannot read %s: %s", path, error)
    return ReadFailed()


def is_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False
