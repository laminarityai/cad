import contextlib
import errno
import os
import re
import secrets
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cad.errors import Unavailable
from cad.records import files, key
from cad.sandbox.outcome import SandboxUnavailable

ATTEMPTS: Final = 8
SLOT_PATTERN: Final = re.compile(r"(\d{4})\.signed")


@dataclass(frozen=True, slots=True)
class Store:
    root: Path
    name: str

    def key_exists(self) -> bool:
        return key.key_path(self.root).is_file()


class StoreUnusable(Unavailable):
    pass


class Tampered(Exception):
    pass


class Contended(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Appended:
    number: int


@dataclass(frozen=True, slots=True)
class Full:
    cap: int


def signed(store: Store, slot: str, record: bytes) -> bytes:
    try:
        return key.sign(store.root, slot, record) + b"\n" + record
    except SandboxUnavailable as error:
        raise _unusable(store) from error


def publish(store: Store, slot: str, path: Path, record: bytes) -> bool:
    """Link the signed record into place. False when another writer already holds the slot."""
    data = signed(store, slot, record)
    temporary = path.parent / f".pending-{secrets.token_hex(8)}"
    try:
        temporary.write_bytes(data)
        os.link(temporary, path)
    except FileExistsError:
        return False
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
    return True


def read(store: Store, slot: str, path: Path) -> bytes | None:
    """The record, or None when the file is missing, not a regular file, or not signed for slot."""
    mac, newline, record = (files.read_regular(path) or b"").partition(b"\n")
    try:
        valid = bool(newline) and key.verify(store.root, slot, record, mac)
    except SandboxUnavailable as error:
        raise _unusable(store) from error
    return record if valid else None


def create_entry(
    store: Store, entry_id: str, first: tuple[str, str, bytes], children: tuple[str, ...]
) -> bool:
    """False when the entry already exists."""
    slot, name, record = first
    incoming = store.root / f".incoming-{secrets.token_hex(8)}"
    try:
        incoming.mkdir(parents=True)
        for child in children:
            (incoming / child).mkdir()
        (incoming / name).write_bytes(signed(store, slot, record))
        try:
            incoming.rename(store.root / entry_id)
        except OSError as error:
            if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                raise
            return False
    finally:
        shutil.rmtree(incoming, ignore_errors=True)
    return True


def append(
    store: Store,
    directory: Path,
    slot_of: Callable[[int], str],
    record_for: Callable[[tuple[bytes, ...]], bytes | None],
    cap: int | None = None,
) -> Appended | Full | None:
    """Take the next numbered slot, <directory>/<n:04d>.signed, with n counting from 1.

    `record_for` sees every record already stored, in order, and returns the bytes to append, or
    None when there is nothing to add. A lost race re-reads and tries again; after ATTEMPTS
    losses it raises Contended. Full when `cap` records are stored. It raises Tampered when a
    stored slot fails its MAC or a number is missing.
    """
    for _ in range(ATTEMPTS):
        existing = read_numbered(store, directory, slot_of)
        if existing is None:
            raise Tampered(str(directory))
        if cap is not None and len(existing) >= cap:
            return Full(cap)
        record = record_for(existing)
        if record is None:
            return None
        number = len(existing) + 1
        if publish(store, slot_of(number), directory / slot_file(number), record):
            return Appended(number)
    raise Contended(str(directory))


def read_numbered(
    store: Store, directory: Path, slot_of: Callable[[int], str]
) -> tuple[bytes, ...] | None:
    """Every record in order. None when a slot fails its MAC, a name is not a slot or a number
    is missing."""
    if not files.is_directory(directory):
        return None
    numbers: list[int] = []
    for path in directory.iterdir():
        if path.name.startswith("."):
            continue
        match = SLOT_PATTERN.fullmatch(path.name)
        if match is None:
            return None
        numbers.append(int(match.group(1)))
    if sorted(numbers) != list(range(1, len(numbers) + 1)):
        return None
    found = [read(store, slot_of(n), directory / slot_file(n)) for n in sorted(numbers)]
    return None if None in found else tuple(record for record in found if record is not None)


def slot_file(number: int) -> str:
    return f"{number:04d}.signed"


def _unusable(store: Store) -> StoreUnusable:
    return StoreUnusable(f"the {store.name} store's key is unusable; the operator must fix it")
