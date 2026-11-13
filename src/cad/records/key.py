import hashlib
import hmac
import logging
import os
import secrets
import stat
from contextlib import suppress
from pathlib import Path
from typing import Final

from cad.sandbox.outcome import SandboxUnavailable

KEY_BYTES: Final = 32
UNUSABLE: Final = (
    "the server cannot use its signing key for variant builds, so it cannot read or store them; "
    "this is a fault on the server, not in the project"
)
LOG = logging.getLogger(__name__)


def key_path(root: Path) -> Path:
    store = root.absolute()
    return store.with_name(f"{store.name}.key")


def sign(root: Path, vid: str, record: bytes) -> bytes:
    path = key_path(root)
    try:
        key = _load_or_create(path)
    except OSError as error:
        raise _unusable(path, error) from error
    return _mac(key, vid, record)


def verify(root: Path, vid: str, record: bytes, mac: bytes) -> bool:
    """False when the store has no key, so a reader never creates one."""
    path = key_path(root)
    try:
        key = _load(path)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise _unusable(path, error) from error
    return hmac.compare_digest(_mac(key, vid, record), mac)


def _mac(key: bytes, vid: str, record: bytes) -> bytes:
    return hmac.new(key, vid.encode() + b"\0" + record, hashlib.sha256).hexdigest().encode()


def _unusable(path: Path, error: OSError) -> SandboxUnavailable:
    LOG.error("cannot use %s: %s", path, error)
    return SandboxUnavailable(UNUSABLE)


def _load_or_create(path: Path) -> bytes:
    with suppress(FileNotFoundError):
        return _load(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}-{secrets.token_hex(8)}")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(secrets.token_bytes(KEY_BYTES))
        with suppress(FileExistsError):
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return _load(path)


def _load(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as file:
        status = os.fstat(file.fileno())
        key = file.read(KEY_BYTES + 1)
    if not stat.S_ISREG(status.st_mode) or status.st_mode & 0o077 or len(key) != KEY_BYTES:
        LOG.error("%s must be a private %d-byte file with mode 0600", path, KEY_BYTES)
        raise SandboxUnavailable(UNUSABLE)
    return key
