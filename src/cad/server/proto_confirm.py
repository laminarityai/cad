"""THROWAWAY prototype for phase 2 PR 1: can a person confirm requirements without the agent?

Two mechanisms. `proto_confirm_elicit` asks the client for a form through MCP elicitation.
`proto_confirm_page` serves a one-time page on 127.0.0.1 and waits for a click on it.
"""

import html
import os
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import anyio
from mcp.server.elicitation import render_elicitation_schema
from mcp.server.mcpserver import Context
from mcp_types import ElicitRequest, ElicitRequestFormParams, ElicitResult, InputRequiredResult
from pydantic import BaseModel, Field

PAGE_WAIT_SECONDS = float(os.environ.get("CAD_PROTO_PAGE_WAIT", "120"))


class Confirmation(BaseModel):
    confirm: bool = Field(description="Tick to confirm every requirement listed above.")


class ConfirmOutcome(BaseModel):
    mechanism: str
    protocol_version: str | None
    client_elicitation: dict[str, Any] | None
    action: str
    content: dict[str, Any] | None
    note: str


def client_elicitation(ctx: Context) -> dict[str, Any] | None:
    caps = ctx.request_context.session.client_capabilities
    if caps is None or caps.elicitation is None:
        return None
    return caps.elicitation.model_dump(mode="json", exclude_none=True)


async def proto_confirm_elicit(
    requirements: list[str], ctx: Context
) -> ConfirmOutcome | InputRequiredResult:
    """PROTOTYPE. Ask the human, through the MCP client, to confirm a list of requirements."""
    caps = client_elicitation(ctx)
    version = ctx.protocol_version
    message = "Confirm these requirements for the design:\n" + "\n".join(
        f"- {r}" for r in requirements
    )
    responses = ctx.input_responses
    if responses is not None:
        answer = responses.get("confirm")
        if not isinstance(answer, ElicitResult):
            return ConfirmOutcome(
                mechanism="elicitation/input_required",
                protocol_version=version,
                client_elicitation=caps,
                action="error",
                content=None,
                note=f"unexpected input response: {answer!r}",
            )
        return ConfirmOutcome(
            mechanism="elicitation/input_required",
            protocol_version=version,
            client_elicitation=caps,
            action=answer.action,
            content=answer.content,
            note="",
        )
    if version is not None and version >= "2026":
        return InputRequiredResult(
            input_requests={
                "confirm": ElicitRequest(
                    params=ElicitRequestFormParams(
                        message=message,
                        requested_schema=render_elicitation_schema(Confirmation),
                    )
                )
            },
            request_state="proto",
        )
    try:
        result = await ctx.elicit(message, Confirmation)
    except Exception as error:  # noqa: BLE001 - the prototype records every failure mode
        return ConfirmOutcome(
            mechanism="elicitation/form",
            protocol_version=version,
            client_elicitation=caps,
            action="error",
            content=None,
            note=f"{type(error).__name__}: {error}",
        )
    content = result.data.model_dump() if result.action == "accept" else None
    return ConfirmOutcome(
        mechanism="elicitation/form",
        protocol_version=version,
        client_elicitation=caps,
        action=result.action,
        content=content,
        note="",
    )


def serve_page(requirements: list[str], token: str) -> tuple[ThreadingHTTPServer, dict[str, str]]:
    answer: dict[str, str] = {}
    items = "".join(f"<li>{html.escape(r)}</li>" for r in requirements)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if query.get("t") != [token] or answer:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"forbidden")
                return
            if url.path == "/answer":
                answer["action"] = query.get("a", ["cancel"])[0]
                body = f"<p>Recorded: {html.escape(answer['action'])}. You can close this tab.</p>"
            else:
                body = (
                    f"<h1>Confirm requirements</h1><ul>{items}</ul>"
                    f'<a href="/answer?t={token}&a=accept">Confirm</a> '
                    f'<a href="/answer?t={token}&a=decline">Decline</a>'
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode())

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, answer


async def proto_confirm_page(requirements: list[str], ctx: Context) -> ConfirmOutcome:
    """PROTOTYPE. Open a local page for the human to confirm requirements, and wait for a click."""
    token = secrets.token_urlsafe(32)
    httpd, answer = serve_page(requirements, token)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/?t={token}"
    url_file = os.environ.get("CAD_PROTO_URL_FILE")
    if url_file:
        Path(url_file).write_text(url)
    else:
        subprocess.run(("open", url), check=False)
    try:
        with anyio.move_on_after(PAGE_WAIT_SECONDS):
            while not answer:
                await anyio.sleep(0.2)
    finally:
        httpd.shutdown()
    return ConfirmOutcome(
        mechanism="local-page",
        protocol_version=ctx.protocol_version,
        client_elicitation=client_elicitation(ctx),
        action=answer.get("action", "timeout"),
        content=None,
        note=f"page served on 127.0.0.1 port {httpd.server_address[1]}",
    )
