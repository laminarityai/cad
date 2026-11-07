"""One open question to a person, and how confirm_requirements waits for the answer.

A ballot is a one-time token, held in memory by this server process, bound to one proposal of
one brief. It is only the right to write that proposal's decision once; the decision itself
lives in the store. Per brief, driven by confirm_requirements calls (C) and page POSTs (P):

    none ----C----------------------> open(n)   new token, page opened, wait up to wait_seconds
    open(n) --P confirm or decline--> spent     decision written; the waiting C returns it
    open(n) --C, n still newest-----> open(n)   same token, page opened again, wait again
    open(n) --C, n+1 proposed-------> retired   open(n+1) instead; n's token gets 403
    open(n) --TTL elapsed-----------> retired   the next C opens a fresh ballot
    any -----C, newest is decided---> no ballot the stored decision is returned

Each C returns within about wait_seconds whatever the person does, then re-reads the store, so
an answer recorded later, or by another server process, reaches the next C. Nothing about a
ballot (token, port, URL) appears in a tool result, an exception message or a log record.
"""

import hmac
import logging
import secrets
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, NewType

import anyio.to_thread

from cad.briefs import store
from cad.briefs.model import BriefId
from cad.briefs.store import BriefRefused, ProposalState

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


@dataclass(slots=True)
class Ballot:
    brief_id: BriefId
    proposal: int
    token: Token
    expires_at: float
    answered: threading.Event = field(default_factory=threading.Event)
    state: Literal["open", "spent", "retired"] = "open"


type Serve = Callable[["Desk"], int]


class Desk:
    """Every ballot of this process, shared by the tool calls and the page's handler threads."""

    def __init__(
        self,
        root: Path,
        opener: Opener,
        serve: Serve,
        wait_seconds: float = WAIT_SECONDS,
        ttl_seconds: float = BALLOT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.root = root
        self._opener = opener
        self._serve = serve
        self._wait_seconds = wait_seconds
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._ballots: dict[BriefId, Ballot] = {}
        self._port: int | None = None

    async def confirm(self, raw_id: str) -> ProposalState:
        """Ask the person about the newest proposal. Its state after the wait: decided or not."""
        state = store.read_state(self.root, raw_id)
        latest = state.latest
        if latest is None:
            raise BriefRefused(
                f"brief {state.brief.id} has no proposed requirements; "
                "call propose_requirements first"
            )
        if latest.decision is not None:
            return latest
        ballot, url = self._open(state.brief.id, latest.proposal.number)
        self._opener(url)
        await anyio.to_thread.run_sync(
            ballot.answered.wait, self._wait_seconds, abandon_on_cancel=True
        )
        after = store.read_state(self.root, state.brief.id).proposal(ballot.proposal)
        if after is None:
            raise store.TamperedBrief(f"brief {state.brief.id} lost proposal {ballot.proposal}")
        return after

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

    def _open(self, brief_id: BriefId, proposal: int) -> tuple[Ballot, PageUrl]:
        with self._lock:
            if self._port is None:
                self._port = self._serve(self)
            ballot = self._ballots.get(brief_id)
            now = self._clock()
            if (
                ballot is None
                or ballot.state != "open"
                or ballot.proposal != proposal
                or ballot.expires_at <= now
            ):
                if ballot is not None and ballot.state == "open":
                    ballot.state = "retired"
                ballot = Ballot(
                    brief_id=brief_id,
                    proposal=proposal,
                    token=Token(secrets.token_urlsafe(32)),
                    expires_at=now + self._ttl_seconds,
                )
                self._ballots[brief_id] = ballot
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
