import hmac
import logging
import secrets
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Literal, NewType

import anyio.to_thread

from cad.confirmations.answers import ItemRef
from cad.confirmations.items import Kinds, pending
from cad.projects.model import ProjectId
from cad.records.roots import Roots

WAIT_SECONDS: Final = 20.0
BALLOT_TTL_SECONDS: Final = 30 * 60.0
Token = NewType("Token", str)
PageUrl = NewType("PageUrl", str)
type Opener = Callable[[PageUrl], None]
LOG = logging.getLogger(__name__)


def program_opener(program: str) -> Opener:
    """Run `program <url>` detached, as `open` does on macOS. The server never waits for it."""

    def open_page(url: PageUrl) -> None:
        try:
            child = subprocess.Popen(
                [program, url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            LOG.error("cannot run the confirmation page opener %s: %s", program, error.strerror)
            return
        threading.Thread(target=child.wait, daemon=True).start()

    return open_page


OS_OPEN: Final = program_opener("open")


@dataclass(slots=True)
class Ballot:
    project: ProjectId
    items: tuple[ItemRef, ...]
    token: Token
    expires_at: float
    answered: threading.Event = field(default_factory=threading.Event)
    state: Literal["open", "spent", "retired"] = "open"


type Serve = Callable[["Desk"], int]


class Desk:
    """Every ballot of this process, shared by the tool calls and the page's handler threads."""

    def __init__(
        self,
        roots: Roots,
        kinds: Kinds,
        opener: Opener,
        serve: Serve,
        wait_seconds: float = WAIT_SECONDS,
        ttl_seconds: float = BALLOT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.roots = roots
        self.kinds = kinds
        self._opener = opener
        self._serve = serve
        self._wait_seconds = wait_seconds
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._ballots: dict[ProjectId, Ballot] = {}
        self._port: int | None = None

    async def ask(self, project: ProjectId) -> None:
        items = pending(self.kinds, project)
        if not items:
            return
        ballot, url = self._open(project, items)
        self._opener(url)
        await anyio.to_thread.run_sync(
            ballot.answered.wait, self._wait_seconds, abandon_on_cancel=True
        )

    def find(self, token: str) -> Ballot | None:
        """The open ballot this token names, for viewing. Viewing spends nothing."""
        with self._lock:
            return self._live(token)

    def spend(self, token: str) -> Ballot | None:
        """Take the open ballot this token names. Of two concurrent calls, one gets it."""
        with self._lock:
            ballot = self._live(token)
            if ballot is not None:
                ballot.state = "spent"
            return ballot

    def retire(self, ballot: Ballot) -> None:
        with self._lock:
            if ballot.state == "open":
                ballot.state = "retired"

    def _open(self, project: ProjectId, items: tuple[ItemRef, ...]) -> tuple[Ballot, PageUrl]:
        with self._lock:
            if self._port is None:
                self._port = self._serve(self)
            ballot = self._ballots.get(project)
            now = self._clock()
            if (
                ballot is None
                or ballot.state != "open"
                or ballot.items != items
                or ballot.expires_at <= now
            ):
                if ballot is not None and ballot.state == "open":
                    ballot.state = "retired"
                ballot = Ballot(
                    project=project,
                    items=items,
                    token=Token(secrets.token_urlsafe(32)),
                    expires_at=now + self._ttl_seconds,
                )
                self._ballots[project] = ballot
            return ballot, PageUrl(f"http://127.0.0.1:{self._port}/confirm/{ballot.token}")

    def _live(self, token: str) -> Ballot | None:
        now = self._clock()
        for ballot in self._ballots.values():
            if not hmac.compare_digest(ballot.token.encode(), token.encode()):
                continue
            if ballot.state == "open" and ballot.expires_at <= now:
                ballot.state = "retired"
            return ballot if ballot.state == "open" else None
        return None
