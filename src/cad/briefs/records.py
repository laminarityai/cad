"""Signed single-file records: a hex HMAC line, then the record bytes.

The MAC covers a slot name, so a record moved to another slot fails. A write is create-exclusive
through `os.link`, so record and MAC land together and the first writer of a slot wins.
"""

import os
import secrets
import stat
from pathlib import Path
from typing import Final

from cad.sandbox.outcome import SandboxUnavailable
from cad.variants import key

MAX_RECORD_BYTES: Final = 1024 * 1024
UNUSABLE: Final = "the brief store's key is unusable; the operator must fix it"


class BriefStoreUnusable(Exception):
    pass


def signed(root: Path, slot: str, record: bytes) -> bytes:
    try:
        return key.sign(root, slot, record) + b"\n" + record
    except SandboxUnavailable as error:
        raise BriefStoreUnusable(UNUSABLE) from error


def publish(root: Path, slot: str, path: Path, record: bytes) -> bool:
    """Link the signed record into place. False when another writer already holds the slot."""
    data = signed(root, slot, record)
    temporary = path.parent.parent / f".pending-{secrets.token_hex(8)}"
    try:
        temporary.write_bytes(data)
        os.link(temporary, path)
    except FileExistsError:
        return False
    finally:
        temporary.unlink(missing_ok=True)
    return True


def read(root: Path, slot: str, path: Path) -> bytes | None:
    """The record, or None when the file is missing, not a regular file, or not signed for slot."""
    mac, newline, record = (_read_regular(path) or b"").partition(b"\n")
    try:
        valid = bool(newline) and key.verify(root, slot, record, mac)
    except SandboxUnavailable as error:
        raise BriefStoreUnusable(UNUSABLE) from error
    return record if valid else None


def is_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _read_regular(path: Path) -> bytes | None:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            return None
        data = file.read(MAX_RECORD_BYTES + 1)
    return None if len(data) > MAX_RECORD_BYTES else data
