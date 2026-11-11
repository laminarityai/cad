import logging
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, NewType
from urllib.parse import urlencode

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId
from cad.projects.model import ProjectId

WAIT_SECONDS: Final = 20.0
POLL_SECONDS: Final = 0.5
PageUrl = NewType("PageUrl", str)
type Opener = Callable[[PageUrl], None]
type PageAddress = Callable[[ProjectId], str]
type OpenPage = Callable[[AccountId, ProjectId], None]
LOG = logging.getLogger(__name__)


def program_opener(program: str) -> Opener:
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


def sign_in_link(
    issuer: LocalIssuer, account: AccountId, project: ProjectId | None = None
) -> PageUrl:
    """The link lands on the project's page, or on the workspace with no project."""
    query = {"token": issuer.mint_person(account)}
    if project is not None:
        query["project"] = project
    return PageUrl(f"{issuer.origin}/local/sign-in?{urlencode(query)}")


def sign_in_opener(issuer: LocalIssuer, opener: Opener) -> OpenPage:
    return lambda account, project: opener(sign_in_link(issuer, account, project))


def page_address(origin: str) -> PageAddress:
    return lambda project: f"{origin.rstrip('/')}/projects/{project}/confirm"


@dataclass(frozen=True, slots=True)
class Door:
    page_url: PageAddress | None = None
    open_page: OpenPage | None = None
    wait_seconds: float = WAIT_SECONDS


class Bell:
    """One per tenant. A recorded answer rings it; the wait also polls, so an answer another
    process recorded is seen within `POLL_SECONDS`."""

    def __init__(self) -> None:
        self._rung = threading.Condition()
        self._rings = 0

    def ring(self) -> None:
        with self._rung:
            self._rings += 1
            self._rung.notify_all()

    def wait(self, until: Callable[[], bool], seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while True:
            with self._rung:
                seen = self._rings
            if until():
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            with self._rung:
                if self._rings == seen:
                    self._rung.wait(min(POLL_SECONDS, remaining))
