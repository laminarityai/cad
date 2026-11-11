import html
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from email.message import Message
from typing import Any, Final
from urllib.parse import urlencode, urlsplit

from cad.accounts.principal import AccountId
from cad.confirmations.waiting import OpenPage
from cad.operations.model import Tenant
from cad.projects.model import ProjectId
from cad.server.app import LocalPage


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class _Stay(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


STAY: Final = urllib.request.build_opener(_Stay)
SNAPSHOT: Final = re.compile(r'name="snapshot" value="([^"]*)"')


def exchange(
    url: str, body: bytes | None = None, headers: Mapping[str, str] | None = None
) -> tuple[int, str, Message]:
    sent = urllib.request.Request(url, data=body, headers=dict(headers or {}))
    try:
        with STAY.open(sent, timeout=5) as response:
            return response.status, response.read().decode(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(), error.headers


def request(
    url: str, body: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int, str]:
    return exchange(url, body, headers)[:2]


def form(answer: str, note: str = "", fields: Mapping[str, str] | None = None) -> bytes:
    return urlencode({"answer": answer, "note": note, **(fields or {})}).encode()


def form_headers(url: str, **headers: str) -> dict[str, str]:
    return {
        "Origin": origin_of(url),
        "Content-Type": "application/x-www-form-urlencoded",
        **headers,
    }


@dataclass
class Person:
    """Plays the user in a browser: follows each sign-in link the server hands its opener, keeps
    the session cookie and the snapshot of the page it last saw, and may answer the page."""

    urls: list[str] = field(default_factory=list[str])
    answer: str | None = None
    delay: float = 0.05
    statuses: list[int] = field(default_factory=list[int])
    cookie: str | None = None
    snapshots: dict[str, str] = field(default_factory=dict[str, str])
    sign_ins: list[str] = field(default_factory=list[str])

    def __call__(self, sign_in: str) -> None:
        self.sign_ins.append(sign_in)
        status, _, headers = exchange(sign_in)
        assert status == 303, status
        self.cookie = headers["Set-Cookie"].split(";")[0]
        url = origin_of(sign_in) + headers["Location"]
        self.get(url)
        self.urls.append(url)
        if self.answer is not None:
            threading.Thread(target=self._answer, args=(url, self.answer), daemon=True).start()

    def _answer(self, url: str, answer: str) -> None:
        time.sleep(self.delay)
        self.statuses.append(self.post(url, answer, "make it lighter")[0])

    @property
    def url(self) -> str:
        return self.urls[-1]

    def signed_in(self, headers: Mapping[str, str]) -> dict[str, str]:
        return {**({} if self.cookie is None else {"Cookie": self.cookie}), **headers}

    def get(self, url: str, **headers: str) -> tuple[int, str]:
        status, body = request(url, headers=self.signed_in(headers))
        shown = SNAPSHOT.search(body)
        if shown is not None:
            self.snapshots[url] = html.unescape(shown.group(1))
        return status, body

    def post(
        self,
        url: str,
        answer: str,
        note: str = "",
        fields: dict[str, str] | None = None,
        **headers: str,
    ) -> tuple[int, str]:
        sealed = {"snapshot": self.snapshots[url]} if url in self.snapshots else {}
        body = form(answer, note, {**sealed, **(fields or {})})
        return request(url, body, self.signed_in(form_headers(url, **headers)))


def local_pages(person: Person, tenant_of: Callable[[AccountId], Tenant]) -> OpenPage:
    """Opens each account's confirmation page on its own loopback server, for `person`."""
    pages: dict[AccountId, LocalPage] = {}

    def open_page(account: AccountId, project: ProjectId) -> None:
        page = pages.setdefault(account, LocalPage(person, lambda: tenant_of(account)))
        page.open(account, project)

    return open_page
