"""The local confirmation page, and the only writer of a decision.

One listener per server process on 127.0.0.1 and a free port, started on the first ballot.

    GET  /confirm/<token>   200 the page, or 403
    POST /confirm/<token>   form body answer=confirm|decline&note=<text>
                            200 recorded, 403, 409 another process already answered, 400, 413

Every auth failure (no token, a wrong, spent or expired one, a ballot a newer proposal retired,
a wrong Host or Origin) gets the same 403 and body. A decision is only ever a POST, so a link
preview or prefetch that fetches the URL cannot answer. Request logging is off, because the token
is in the request line.
"""

import html
import logging
import re
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final, cast
from urllib.parse import parse_qs

from cad.briefs import store
from cad.briefs.ballot import Ballot, Desk
from cad.briefs.model import (
    MAX_NOTE_CHARS,
    Answer,
    BriefId,
    Confirmed,
    Decision,
    Declined,
    deciding_check,
    describe,
)
from cad.briefs.store import BriefRefused, BriefState, ProposalState
from cad.records import signed
from cad.records.roots import Roots
from cad.records.signed import StoreUnusable

TOKEN_PATH: Final = re.compile(r"/confirm/([A-Za-z0-9_-]{1,128})")
MAX_BODY_BYTES: Final = 8 * 1024
FORBIDDEN: Final = "This page is not open. Ask the agent to open the confirmation page again."
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
STYLE: Final = (
    "body{font:16px/1.5 system-ui,sans-serif;max-width:44rem;margin:2rem auto;padding:0 1rem}"
    "blockquote{white-space:pre-wrap;border-left:4px solid #888;margin:0;padding:.5rem 1rem}"
    ".check{color:#555}li{margin:.75rem 0}textarea{width:100%;min-height:4rem}"
    "button{font-size:1rem;margin:.5rem .5rem 0 0;padding:.4rem 1rem}"
)
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
    """Start the listener for this desk on a daemon thread and return its port."""
    server = _Server(desk)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.port


class _Handler(BaseHTTPRequestHandler):
    @property
    def _page(self) -> _Server:
        return cast(_Server, self.server)

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        ballot = self._page.desk.find(self._token() or "") if self._host_ok() else None
        if ballot is None:
            return self._send(403, _plain(FORBIDDEN))
        try:
            state = store.read_state(self._page.desk.roots, ballot.brief_id)
        except (BriefRefused, StoreUnusable):
            return self._send(500, _plain("The brief store refused this brief. Tell the agent."))
        proposed = _still_open(state, ballot)
        if proposed is None:
            return self._send(403, _plain(FORBIDDEN))
        self._send(200, render(state, proposed, ballot))

    def do_POST(self) -> None:
        origin = f"http://127.0.0.1:{self._page.port}"
        token = self._token()
        if not self._host_ok() or self.headers.get("Origin") != origin or token is None:
            return self._send(403, _plain(FORBIDDEN))
        length = self.headers.get("Content-Length", "")
        if not length.isdigit():
            return self._send(400, _plain("The answer was not sent as a form."))
        if int(length) > MAX_BODY_BYTES:
            return self._send(413, _plain("The note is too long."))
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip()
        answer = _answer(self.rfile.read(int(length)))
        if content_type != "application/x-www-form-urlencoded" or answer is None:
            return self._send(400, _plain("The answer was not sent as a form."))
        ballot = self._page.desk.spend(token)
        if ballot is None:
            return self._send(403, _plain(FORBIDDEN))
        try:
            outcome = _record(self._page.desk, ballot, answer)
        except (BriefRefused, StoreUnusable):
            return self._send(500, _plain("The brief store refused this answer. Tell the agent."))
        if outcome is None:
            return self._send(403, _plain(FORBIDDEN))
        ballot.answered.set()
        if outcome != answer:
            return self._send(409, _plain("Someone already answered this proposal differently."))
        said = "confirmed" if isinstance(answer, Confirmed) else "declined"
        self._send(200, _plain(f"Recorded: you {said} the requirements. Return to the chat."))

    def _host_ok(self) -> bool:
        return self.headers.get("Host") == f"127.0.0.1:{self._page.port}"

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


def _still_open(state: BriefState, ballot: Ballot) -> ProposalState | None:
    """The ballot's proposal, unless a newer one retired it or it is already decided."""
    latest = state.latest
    if latest is None or latest.proposal.number != ballot.proposal or latest.answered is not None:
        return None
    return latest


def _answer(body: bytes) -> Answer | None:
    try:
        form = parse_qs(body.decode(), keep_blank_values=True, strict_parsing=True)
    except (UnicodeDecodeError, ValueError):
        return None
    answers = form.get("answer", [])
    notes = form.get("note", [""])
    if set(form) - {"answer", "note"} or len(answers) != 1 or len(notes) != 1:
        return None
    if len(notes[0]) > MAX_NOTE_CHARS:
        return None
    match answers[0]:
        case "confirm":
            return Confirmed()
        case "decline":
            return Declined(note=notes[0])
        case _:
            return None


def _record(desk: Desk, ballot: Ballot, answer: Answer) -> Answer | None:
    """Write the decision; the stored answer, or None when the ballot is no longer open."""
    state = store.read_state(desk.roots, ballot.brief_id)
    proposed = state.latest
    if proposed is None or proposed.proposal.number != ballot.proposal:
        return None
    decision = Decision(
        proposal=ballot.proposal,
        brief_sha256=state.brief_sha256,
        proposal_sha256=proposed.sha256,
        answer=answer,
        decided_at=datetime.now(UTC),
    )
    return record_decision(desk.roots, ballot.brief_id, decision)


def record_decision(roots: Roots, brief_id: BriefId, decision: Decision) -> Answer:
    """Store the person's answer for a proposal; if one is already stored, return that one."""
    number = decision.proposal
    path = roots.briefs / brief_id / store.DECISIONS / signed.slot_file(number)
    record = decision.model_dump_json().encode()
    signed.publish(
        signed.Store(roots.briefs, "brief"), f"{brief_id}/decision/{number}", path, record
    )
    stored = store.read_state(roots, brief_id).proposal(number)
    if stored is None or stored.answered is None:
        raise store.TamperedBrief(f"brief {brief_id}: decision {number} did not persist")
    return stored.answered.answer


def render(state: BriefState, proposed: ProposalState, ballot: Ballot) -> bytes:
    """The page. Everything shown comes from the store, never from tool arguments."""
    text = state.brief.text
    rows: list[str] = []
    for requirement in proposed.proposal.requirements:
        check = deciding_check(requirement.target.kind)
        decided = f"Decided by the {check} check" if check else "No reviewed check: unverified"
        quote = text[requirement.origin.start : requirement.origin.end]
        rows.append(
            f"<li><strong>{html.escape(describe(requirement))}</strong><br>"
            f'From your words: <q class="origin">{html.escape(quote)}</q><br>'
            f'<span class="check">{decided}</span></li>'
        )
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<title>Confirm requirements</title>"
        f"<style>{STYLE}</style></head><body>"
        "<h1>Confirm the requirements for your brief</h1>"
        "<p>Your brief, as the agent stored it:</p>"
        f'<blockquote class="brief">{html.escape(text)}</blockquote>'
        f"<p>The agent proposed these requirements (proposal {proposed.proposal.number}). "
        "Confirm only if your brief is right and every requirement says what you "
        "want. Checks will read these numbers.</p>"
        f"<ol>{''.join(rows)}</ol>"
        f'<form method="post" action="/confirm/{ballot.token}">'
        '<label for="note">Note to the agent, if you decline</label>'
        f'<textarea id="note" name="note" maxlength="{MAX_NOTE_CHARS}"></textarea>'
        '<button name="answer" value="confirm">Confirm all</button>'
        '<button name="answer" value="decline">Decline</button>'
        "</form></body></html>"
    ).encode()


def _plain(message: str) -> bytes:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8><title>Confirmation</title>"
        f"<style>{STYLE}</style></head><body><p>{html.escape(message)}</p></body></html>"
    ).encode()
