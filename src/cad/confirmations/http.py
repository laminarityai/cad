"""The local transport for the confirmation page.

    GET  /confirm/<token>   200 the page, 403, or 409 the project changed since it opened
    POST /confirm/<token>   form body answer=confirm|decline&note=<text>[&edit-<i>-<row>=<text>]
                            200 recorded, 403, 409 already answered or changed, 400, 413

Request logging is off, because the token is in the request line.
"""

import logging
import re
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final, cast

from cad.briefs.store import BriefRefused
from cad.confirmations import page
from cad.confirmations.ballot import Desk
from cad.confirmations.page import AlreadyAnswered, Changed, Recorded, plain
from cad.projects.model import ProjectRefused
from cad.records.signed import StoreUnusable

TOKEN_PATH: Final = re.compile(r"/confirm/([A-Za-z0-9_-]{1,128})")
MAX_BODY_BYTES: Final = 8 * 1024
FORBIDDEN: Final = "This page is not open. Ask the agent to open the confirmation page again."
CHANGED: Final = (
    "The agent added or changed something since this page opened. Nothing was recorded. "
    "Ask the agent to open the page again."
)
REFUSED: Final = "The store refused this page. Tell the agent."
NOT_A_FORM: Final = "The answer was not sent as a form."
# The page posts to itself. A no-referrer policy would make browsers send `Origin: null` on that
# POST, so same-origin keeps the Origin check usable while sending no referrer anywhere else.
HEADERS: Final = (
    ("Cache-Control", "no-store"),
    ("Referrer-Policy", "same-origin"),
    (
        "Content-Security-Policy",
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
    ),
    ("X-Content-Type-Options", "nosniff"),
)
STORE_FAILURES: Final = (BriefRefused, ProjectRefused, StoreUnusable)
LOG = logging.getLogger(__name__)


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, desk: Desk) -> None:
        self.desk = desk
        super().__init__(("127.0.0.1", 0), _Handler)

    @property
    def port(self) -> int:
        return self.server_address[1]

    def handle_error(self, request: object, client_address: object) -> None:
        LOG.error("the confirmation page failed a request: %s", sys.exc_info()[0])


def serve(desk: Desk) -> int:
    server = _Server(desk)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.port


class _Handler(BaseHTTPRequestHandler):
    @property
    def _desk(self) -> Desk:
        return cast(_Server, self.server).desk

    @property
    def _port(self) -> int:
        return cast(_Server, self.server).port

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        ballot = self._desk.find(self._token() or "") if self._host_ok() else None
        if ballot is None:
            return self._send(403, plain(FORBIDDEN))
        try:
            shown = page.view(self._desk.kinds, ballot)
        except STORE_FAILURES:
            return self._send(500, plain(REFUSED))
        if isinstance(shown, Changed):
            self._desk.retire(ballot)
            return self._send(409, plain(CHANGED))
        self._send(200, shown)

    def do_POST(self) -> None:
        token = self._token()
        origin = f"http://127.0.0.1:{self._port}"
        if not self._host_ok() or self.headers.get("Origin") != origin or token is None:
            return self._send(403, plain(FORBIDDEN))
        length = self.headers.get("Content-Length", "")
        if not length.isdigit():
            return self._send(400, plain(NOT_A_FORM))
        if int(length) > MAX_BODY_BYTES:
            return self._send(413, plain("The note is too long."))
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip()
        body = self.rfile.read(int(length))
        ballot = self._desk.find(token)
        if ballot is None:
            return self._send(403, plain(FORBIDDEN))
        form = page.parse_form(body, len(ballot.items))
        if content_type != "application/x-www-form-urlencoded" or form is None:
            return self._send(400, plain(NOT_A_FORM))
        refusal = page.refused_edits(self._desk.kinds, ballot.items, form)
        if refusal is not None:
            return self._send(400, plain(refusal))
        if self._desk.spend(token) is not ballot:
            return self._send(403, plain(FORBIDDEN))
        try:
            outcome = page.answer_page(
                self._desk.roots, self._desk.kinds, ballot, form, datetime.now(UTC)
            )
        except STORE_FAILURES:
            return self._send(500, plain(REFUSED))
        finally:
            ballot.answered.set()
        match outcome:
            case Recorded(verdict="confirmed"):
                said = "Recorded: you confirmed everything on this page. Return to the chat."
                self._send(200, plain(said))
            case Recorded():
                said = "Recorded: you declined everything on this page. Return to the chat."
                self._send(200, plain(said))
            case AlreadyAnswered():
                self._send(409, plain("This page was already answered."))
            case Changed():
                self._send(409, plain(CHANGED))

    def _host_ok(self) -> bool:
        return self.headers.get("Host") == f"127.0.0.1:{self._port}"

    def _token(self) -> str | None:
        match = TOKEN_PATH.fullmatch(self.path)
        return None if match is None else match.group(1)

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in HEADERS:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)
