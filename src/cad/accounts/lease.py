"""The exclusive lease on the hosted data root.

Phase 4 runs one replica: the check lanes and their semaphore live in one process's memory. The
HTTP server holds an flock on `<accounts>/lease` for its whole life, so a second server on the same
root refuses to start. The kernel releases the lock when the process exits in any way, so a crash
leaves no stale lease. Only the HTTP server takes it: two stdio servers on one home stay supported.
"""

import fcntl
import os
from pathlib import Path
from typing import Final, TextIO

LEASE: Final = "lease"


class LeaseHeld(Exception):
    pass


def take(accounts: Path) -> TextIO:
    """Returns the open lease file; it must stay referenced for as long as the server runs."""
    accounts.mkdir(parents=True, exist_ok=True)
    path = accounts / LEASE
    file = path.open("a+")
    try:
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        file.seek(0)
        holder = file.read().strip() or "another process"
        file.close()
        raise LeaseHeld(
            f"{path} is held by {holder}: one server serves a data root, so this one did not start"
        ) from error
    file.truncate(0)
    file.write(f"pid {os.getpid()}\n")
    file.flush()
    return file
