"""The confirmation page in the signed-in web app.

    GET  /projects/<pid>/confirm   200 the page, or a page saying nothing waits; 401 the sign-in
                                   page; 404 no such project in the person's own account
    POST /projects/<pid>/confirm   form snapshot=<sealed>&answer=confirm|decline&note=<text>
                                   [&decline-<i>=decline][&edit-<i>-<row>=<text>]
                                   200 recorded, 400, 401, 403, 404, 409, 413, 500 nothing recorded
    GET  /local/sign-in?token=<person JWT>&project=<pid>
                                   303 to the page with the session cookie; only when the server
                                   trusts the local issuer

Only a person session passes, so an agent's access token gets 401. No log record carries the
token or the cookie.
"""

import html
import logging
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

import anyio.to_thread
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId, PersonSession
from cad.accounts.tokens import Verifier
from cad.briefs.store import BriefRefused
from cad.confirmations import page, snapshot
from cad.confirmations.items import pending
from cad.confirmations.page import STYLE, plain
from cad.confirmations.registry import kinds
from cad.operations.confirmation import AnswerPageInput, PageReply
from cad.operations.model import Tenant
from cad.operations.registry import OPERATIONS
from cad.operations.routes import SESSION_COOKIE, session_token
from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId, ProjectRefused, parse_project_id
from cad.records.signed import StoreUnusable
from cad.sandbox.meter import metered
from cad.sandbox.outcome import SandboxUnavailable

MAX_BODY_BYTES: Final = 64 * 1024
CSP: Final = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"
)
# The page posts to itself. A no-referrer policy would make browsers send `Origin: null` on that
# POST, so same-origin keeps the Origin check usable while sending no referrer anywhere else.
HEADERS: Final = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": CSP,
}
STATUS: Final[Mapping[str, int]] = {
    "recorded": 200,
    "already_answered": 409,
    "changed": 409,
    "refused": 400,
    "forbidden": 403,
}
STORE_FAILURES: Final = (BriefRefused, ProjectRefused, StoreUnusable, SandboxUnavailable)
NOTHING_WAITS: Final = "Nothing in this project waits on you."
NO_PROJECT: Final = "There is no such project in your account."
FORBIDDEN: Final = "This answer did not come from this page."
REFUSED: Final = (
    "The answer did not go through, and nothing was recorded. Try again, or tell the agent."
)
NOT_A_FORM: Final = "The answer was not sent as a form."
LOCAL_SIGN_IN: Final = (
    "Sign in with the link the server handed its opener. Ask the agent to call ask_to_confirm "
    "again for a new one."
)
CLERK_JS: Final = "/npm/@clerk/clerk-js@5.128.1/dist/clerk.browser.js"
# Clerk's CSP guide names these hosts for clerk-js: bot protection and fraud protection.
CLERK_CHALLENGES: Final = "https://challenges.cloudflare.com https://*.protect.clerk.com"
# A signed-in person goes back to the page by GET, so a POST that met an expired token is never
# sent again by a reload.
SIGN_IN_SCRIPT: Final = (
    "(async () => { await Clerk.load(); if (Clerk.user) { location.replace(location.href); } "
    "else { Clerk.mountSignIn(document.getElementById('sign-in'), "
    "{ forceRedirectUrl: location.href }); } })();"
)
# A Clerk session token lasts about a minute. Loaded Clerk keeps `__session` fresh while the page
# is open.
KEEP_SESSION_SCRIPT: Final = (
    "const ready = Promise.resolve().then(() => Clerk.load());"
    "const form = document.getElementById('page');"
    "const key = 'cad-draft:' + form.elements.snapshot.value.split('.')[0];"
    "const fields = () => [...form.elements].filter((one) =>"
    " one.name && one.name !== 'snapshot' && one.type !== 'submit');"
    "const keep = () => { try { sessionStorage.setItem(key, JSON.stringify(Object.fromEntries("
    "fields().map((one) => [one.name, one.type === 'checkbox' ? one.checked : one.value])))); }"
    " catch {} };"
    "try { const kept = JSON.parse(sessionStorage.getItem(key) || '{}');"
    " for (const one of fields()) { if (!(one.name in kept)) { continue; }"
    " if (one.type === 'checkbox') { one.checked = kept[one.name]; }"
    " else { one.value = kept[one.name]; } } } catch {}"
    "document.addEventListener('input', keep);"
    "document.addEventListener('change', keep);"
    "form.addEventListener('submit', async (event) => {"
    " keep();"
    " if (form.dataset.fresh) { return; }"
    " event.preventDefault();"
    " await ready.then(() => Clerk.session?.getToken({ skipCache: true })).catch(() => null);"
    " form.dataset.fresh = 'yes';"
    " form.requestSubmit(event.submitter);"
    "});"
)
LOG = logging.getLogger(__name__)

type TenantOf = Callable[[AccountId], Tenant]


@dataclass(frozen=True, slots=True)
class LocalSignIn:
    issuer: LocalIssuer


@dataclass(frozen=True, slots=True)
class ClerkSignIn:
    frontend_api: str
    publishable_key: str


type SignIn = LocalSignIn | ClerkSignIn


def confirm_routes(
    verifier: Verifier, tenant_of: TenantOf, origin: str, sign_in: SignIn
) -> list[Route]:
    answer = next(one for one in OPERATIONS if one.name == "answer_page")

    def signed_in(request: Request) -> tuple[PersonSession, Tenant, ProjectId] | Response:
        person = verifier.person(session_token(request))
        if person is None:
            return _sign_in_page(sign_in)
        tenant = tenant_of(person.account)
        try:
            project = parse_project_id(request.path_params["project_id"])
        except ProjectRefused:
            return _plain(404, NO_PROJECT)
        if tenant.account != person.account:
            return _plain(404, NO_PROJECT)
        return person, tenant, project

    async def show(request: Request) -> Response:
        found = signed_in(request)
        if isinstance(found, Response):
            return found
        try:
            return await anyio.to_thread.run_sync(_show, *found, sign_in)
        except STORE_FAILURES as error:
            LOG.error("the confirmation page could not be shown: %s", type(error).__name__)
            return _plain(500, REFUSED)

    async def record(request: Request) -> Response:
        found = signed_in(request)
        if isinstance(found, Response):
            return found
        person, tenant, project = found
        if request.headers.get("origin") != origin:
            return _plain(403, FORBIDDEN)
        body = await _body(request)
        if body is None:
            return _plain(413, "The answer is too long.")
        content_type = request.headers.get("content-type", "").split(";")[0].strip()
        if content_type != "application/x-www-form-urlencoded":
            return _plain(400, NOT_A_FORM)
        try:
            arguments = AnswerPageInput(project_id=project, person=person, form=body)
        except ValidationError:
            return _plain(404, NO_PROJECT)

        def run() -> object:
            with metered(tenant.meter):
                return answer.run(tenant, arguments)

        try:
            reply = await anyio.to_thread.run_sync(run)
        except Exception as error:
            # Nothing past the answer's link into place raises, so nothing was recorded and the
            # same form can be sent again.
            LOG.error("the confirmation page could not record an answer: %r", error)
            return _plain(500, REFUSED)
        assert isinstance(reply, PageReply)
        if reply.outcome == "recorded":
            tenant.bell.ring()
        return _plain(STATUS[reply.outcome], *reply.said)

    routes = [
        Route("/projects/{project_id}/confirm", show, methods=["GET"]),
        Route("/projects/{project_id}/confirm", record, methods=["POST"]),
    ]
    if isinstance(sign_in, LocalSignIn):
        routes.append(Route("/local/sign-in", _local_sign_in(verifier), methods=["GET"]))
    return routes


def _show(person: PersonSession, tenant: Tenant, project: ProjectId, sign_in: SignIn) -> Response:
    if not project_briefs(tenant.roots, project):
        return _plain(404, NO_PROJECT)
    every = kinds(tenant.roots)
    items = pending(every, project)
    if not items:
        return _plain(200, NOTHING_WAITS)
    sealed = snapshot.seal(tenant.roots.projects, person, project, items)
    if isinstance(sign_in, LocalSignIn):
        return _html(200, page.view(tenant.roots, every, project, items, sealed, ""))
    scripts, policy = _clerk_scripts_and_policy(sign_in, KEEP_SESSION_SCRIPT)
    return _html(200, page.view(tenant.roots, every, project, items, sealed, scripts), policy)


def _local_sign_in(verifier: Verifier) -> Callable[[Request], Response]:
    def sign_in(request: Request) -> Response:
        token = request.query_params.get("token", "")
        if verifier.person(token) is None:
            return _plain(401, LOCAL_SIGN_IN)
        try:
            project = parse_project_id(request.query_params.get("project", ""))
        except ProjectRefused:
            return _plain(400, NO_PROJECT)
        response = RedirectResponse(f"/projects/{project}/confirm", 303, headers=HEADERS)
        response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", path="/")
        return response

    return sign_in


async def _body(request: Request) -> bytes | None:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return None
    read = bytearray()
    async for chunk in request.stream():
        read += chunk
        if len(read) > MAX_BODY_BYTES:
            return None
    return bytes(read)


def _sign_in_page(sign_in: SignIn) -> Response:
    if isinstance(sign_in, LocalSignIn):
        return _plain(401, LOCAL_SIGN_IN)
    scripts, policy = _clerk_scripts_and_policy(sign_in, SIGN_IN_SCRIPT)
    body = (
        "<!doctype html><html lang=en><head><meta charset=utf-8><title>Sign in</title>"
        f"<style>{STYLE}</style></head><body>"
        "<p>Sign in to see what the agent asks you to confirm.</p><div id=sign-in></div>"
        f"{scripts}</body></html>"
    )
    return _html(401, body.encode(), policy)


def _clerk_scripts_and_policy(sign_in: ClerkSignIn, inline: str) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    api = sign_in.frontend_api
    scripts = (
        f'<script nonce="{nonce}" crossorigin="anonymous" '
        f'data-clerk-publishable-key="{html.escape(sign_in.publishable_key)}" '
        f'src="{html.escape(api + CLERK_JS)}"></script>'
        f'<script nonce="{nonce}">{inline}</script>'
    )
    policy = (
        f"{CSP}; script-src {api} {CLERK_CHALLENGES} 'nonce-{nonce}'; "
        f"connect-src {api} https://*.protect.clerk.com:*; img-src {api} https://img.clerk.com; "
        f"worker-src 'self' blob:; frame-src {api} {CLERK_CHALLENGES}"
    )
    return scripts, {"Content-Security-Policy": policy}


def _plain(status: int, message: str, *more: str) -> Response:
    return _html(status, plain(message, *more))


def _html(status: int, body: bytes, headers: Mapping[str, str] | None = None) -> Response:
    return HTMLResponse(body, status, headers={**HEADERS, **(headers or {})})
