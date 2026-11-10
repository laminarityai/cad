"""The cad server over HTTP: `/mcp` for agents, `/v1/...` for the signed-in person.

Clerk is the authorization server and this server is only the resource server. `/mcp` takes a
Clerk OAuth access token and serves the Protected Resource Metadata (RFC 9728) that names the
Clerk instance. A web route takes a Clerk session token. Each kind gets 401 on the other's route.

With no Clerk configuration, the server trusts the local issuer instead, and only when it listens
on a loopback address. The data root is leased for the server's life, and every container any
call starts is charged to the caller's account before it starts.
"""

import argparse
import ipaddress
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import uvicorn
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from cad.accounts import lease
from cad.accounts.clerk import PUBLIC_URL, PUBLISHABLE_KEY, clerk_issuer
from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AgentToken
from cad.accounts.tenants import ACCOUNTS, Tenants
from cad.accounts.tokens import Issuer, Verifier
from cad.chat.model import Model, from_environment
from cad.chat.routes import Chat, chat_routes
from cad.confirmations.ballot import Opener, program_opener
from cad.context_parts.ingest import ingest as read_part
from cad.context_parts.store import Ingest
from cad.conversations import store
from cad.operations.guidance import INSTRUCTIONS
from cad.operations.model import Tenant
from cad.operations.registry import OPERATIONS, ROUTES
from cad.operations.routes import person_routes
from cad.operations.tools import tools
from cad.records.roots import DATA_ROOT
from cad.sandbox import container, meter
from cad.sandbox.outcome import SandboxUnavailable

DAILY_CAP_SECONDS: Final = 3600
PORT: Final = 8765
WAIT_SECONDS: Final = 20.0
GRACEFUL_SHUTDOWN_SECONDS: Final = 3


class AgentAccess(AccessToken):
    agent: AgentToken


@dataclass(frozen=True, slots=True)
class AgentTokens:
    """The SDK's `TokenVerifier` for `/mcp`: only a Clerk OAuth access token whose `aud` includes
    our `/mcp` URL passes."""

    verifier: Verifier

    async def verify_token(self, token: str) -> AccessToken | None:
        agent = self.verifier.agent(token)
        if agent is None:
            return None
        return AgentAccess(
            token=token,
            client_id=agent.client_id,
            scopes=[],
            resource=self.verifier.issuer.resource,
            subject=agent.account,
            agent=agent,
        )


def build_app(issuer: Issuer, tenants: Tenants, model: Model | None = None) -> Starlette:
    """`model` runs the chat agent. None reads `CAD_CHAT_MODEL`, so a server with no model
    configured still starts and answers every call but a chat message."""
    verifier = Verifier(issuer)
    chat = Chat(model or from_environment(os.environ), tenants)

    def tenant_of_token() -> Tenant:
        token = get_access_token()
        if not isinstance(token, AgentAccess):
            raise PermissionError("an MCP call reached a tool with no verified agent token")
        return store.bind(tenants.of(token.agent.account), token.agent.conversation)

    server = MCPServer(
        "cad",
        instructions=INSTRUCTIONS,
        tools=tools(tenant_of_token, OPERATIONS),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(issuer.url),
            resource_server_url=AnyHttpUrl(issuer.resource),
            validate_token_resource=False,
        ),
        token_verifier=AgentTokens(verifier),
    )
    public = urlsplit(issuer.resource)
    app = server.streamable_http_app(
        transport_security=TransportSecuritySettings(
            allowed_hosts=[public.netloc],
            allowed_origins=[f"{public.scheme}://{public.netloc}"],
        )
    )
    app.router.routes.insert(0, _resource_metadata(issuer))
    app.router.routes.extend(person_routes(OPERATIONS, ROUTES, verifier.person, tenants.of))
    app.router.routes.extend(chat_routes(verifier.person, chat))
    app.state.chat = chat
    return app


def _resource_metadata(issuer: Issuer) -> Route:
    """RFC 9728 metadata naming Clerk's issuer exactly as its tokens' `iss` does. The SDK's own
    route holds it as a pydantic URL, which appends `/` to a bare origin, and Clerk refuses an
    authorization server that does not match its issuer. This route is matched first."""
    metadata = {
        "resource": issuer.resource,
        "authorization_servers": [issuer.url],
        "bearer_methods_supported": ["header"],
    }

    async def handle(_: Request) -> JSONResponse:
        return JSONResponse(metadata, headers={"Cache-Control": "public, max-age=3600"})

    return Route(
        f"/.well-known/oauth-protected-resource{urlsplit(issuer.resource).path}",
        handle,
        methods=["GET"],
    )


def choose_issuer(root: Path, host: str, port: int, environ: Mapping[str, str]) -> Issuer:
    clerk = clerk_issuer(environ)
    if clerk is not None:
        return clerk
    if not _loopback(host):
        raise SystemExit(
            f"cad-http: no Clerk instance is configured, so it serves only on a loopback address; "
            f"set {PUBLISHABLE_KEY} and {PUBLIC_URL} to serve on {host}"
        )
    return LocalIssuer.open(root, f"http://{host}:{port}").issuer()


def _loopback(host: str) -> bool:
    try:
        return host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def serve(
    root: Path,
    host: str,
    port: int,
    cap_seconds: int,
    opener: Opener,
    ingest: Ingest = read_part,
    environ: Mapping[str, str] = os.environ,
) -> None:
    issuer = choose_issuer(root, host, port, environ)
    try:
        held = lease.take(root / ACCOUNTS)
    except lease.LeaseHeld as error:
        raise SystemExit(f"cad-http: {error}") from error
    meter.require()
    with suppress(SandboxUnavailable):
        container.remove_orphans()
    tenants = Tenants(root / ACCOUNTS, cap_seconds, opener, WAIT_SECONDS, ingest)
    logging.getLogger(__name__).info("serving %s, tokens from %s", issuer.resource, issuer.url)
    with held:
        uvicorn.run(
            build_app(issuer, tenants),
            host=host,
            port=port,
            log_level="warning",
            timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cad-http", description="The cad server over HTTP.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--root", type=Path, default=DATA_ROOT, help="the data root (~/.cad)")
    parser.add_argument(
        "--cap-seconds",
        type=int,
        default=DAILY_CAP_SECONDS,
        help=f"container-seconds each account may use per UTC day (default {DAILY_CAP_SECONDS})",
    )
    parser.add_argument("--opener", default="open", metavar="PROGRAM")
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    serve(args.root, args.host, args.port, args.cap_seconds, program_opener(args.opener))
    return 0


if __name__ == "__main__":
    sys.exit(main())
