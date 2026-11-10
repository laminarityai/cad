"""Clerk session expiry repro for the hosted confirmation page.

A stand-in Clerk Frontend API on its own port serves `clerk.browser.js` and mints person tokens
from the local issuer with a 10 s TTL and one Clerk session id, the way Clerk refreshes a
session. Nothing refreshes on a timer, so only the page's own pre-submit refresh can keep the
POST signed in.

    uv run python .claude/skills/verify/scripts/clerk_session.py <out dir> expired|signed-out

`expired` lets the token lapse while the person types, then confirms. `signed-out` also ends the
Clerk session, so the POST meets sign-in, signs in again under a new session, and confirms the
restored edits. Each case writes `<case>.json` and screenshots into the out dir. Run it from an
older checkout with `PYTHONPATH=<that checkout>/src` for a baseline.
"""

import asyncio
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.async_api import async_playwright
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId
from cad.accounts.tenants import Tenants
from cad.confirmations.waiting import Door
from cad.confirmations.web import CLERK_JS, ClerkSignIn
from cad.context_parts.ingest import ingest
from cad.operations.briefs import (
    CreateBriefInput,
    ListRequirementsInput,
    ProposeRequirementsInput,
    RequirementDraft,
    create_brief,
    list_requirements,
    propose_requirements,
)
from cad.server.hosted import build_app

TTL = 10
ALICE = AccountId("user_alice")
FAKE_CLERK = """
window.Clerk = {
  user: null, session: null,
  async token() {
    const sent = await fetch(FAPI + '/token');
    if (!sent.ok) { return null; }
    const token = await sent.text();
    document.cookie = '__session=' + token + '; path=/';
    return token;
  },
  async load() {
    if (await this.token()) {
      this.user = {};
      this.session = { getToken: () => this.token() };
    }
  },
  mountSignIn(where, options) {
    const button = document.createElement('button');
    button.id = 'fake-sign-in';
    button.textContent = 'Sign in (stand-in Clerk)';
    button.onclick = async () => {
      await fetch(FAPI + '/sign-in');
      location.href = options.forceRedirectUrl;
    };
    where.append(button);
  },
};
"""


def port() -> socket.socket:
    listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listening.bind(("127.0.0.1", 0))
    return listening


def serve(app: Starlette, listening: socket.socket) -> None:
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    threading.Thread(target=server.run, args=([listening],), daemon=True).start()
    while not server.started:
        time.sleep(0.05)


async def main(out: Path, case: str) -> int:
    out.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="clerk-ttl-"))
    app_port, fapi_port = port(), port()
    base = f"http://127.0.0.1:{app_port.getsockname()[1]}"
    fapi = f"http://127.0.0.1:{fapi_port.getsockname()[1]}"
    local = LocalIssuer.open(root, base)
    state = {"signed_in": True, "session": "sess_reads_for_a_long_time", "minted": 0}

    def token(_: Request) -> Response:
        cors = {"Access-Control-Allow-Origin": base}
        if not state["signed_in"]:
            return PlainTextResponse("signed out", 401, headers=cors)
        state["minted"] = int(state["minted"]) + 1
        try:
            minted = local.mint_person(ALICE, TTL, str(state["session"]))
        except TypeError:  # the PR head before this round mints a new session id each time
            minted = local.mint_person(ALICE, TTL)
        return PlainTextResponse(minted, headers=cors)

    def sign_in(_: Request) -> Response:
        state.update(signed_in=True, session="sess_signed_in_again")
        return PlainTextResponse("ok", headers={"Access-Control-Allow-Origin": base})

    def script(_: Request) -> Response:
        body = f"const FAPI = {json.dumps(fapi)};" + FAKE_CLERK
        return Response(
            body, media_type="text/javascript", headers={"Access-Control-Allow-Origin": base}
        )

    serve(
        Starlette(
            routes=[
                Route(CLERK_JS, script),
                Route("/token", token),
                Route("/sign-in", sign_in),
            ]
        ),
        fapi_port,
    )
    tenants = Tenants(root / "accounts", 60, Door(wait_seconds=0.3), ingest)
    serve(build_app(local.issuer(), tenants, ClerkSignIn(fapi, "pk_test_stand_in")), app_port)
    alice = tenants.of(ALICE)
    brief = create_brief(alice, CreateBriefInput(text="A wall hook under 150 g, printed in PLA."))
    draft = RequirementDraft.model_validate(
        {
            "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
            "quote": "under 150 g",
        }
    )
    propose_requirements(
        alice, ProposeRequirementsInput(brief_id=brief.brief_id, requirements=[draft])
    )
    url = f"{base}/projects/{brief.project_id}/confirm"
    log: list[dict[str, object]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        page.on("console", lambda message: log.append({"console": message.text}))
        page.on(
            "response",
            lambda response: log.append(
                {"status": response.status, "url": response.url, "method": response.request.method}
            ),
        )
        await page.goto(url)
        await page.wait_for_selector("form#page", timeout=8000)
        edit = page.locator("input[name^=edit-]").first
        await edit.fill("120 g")
        await page.fill("#note", "kept through the expiry")
        if case == "signed-out":
            state["signed_in"] = False
        await asyncio.sleep(TTL + 5)
        async with page.expect_navigation():
            await page.click("button[value=confirm]")
        if case == "signed-out":
            await page.screenshot(path=str(out / f"{case}-sign-in.png"))
            await page.click("#fake-sign-in")
            await page.wait_for_selector("form#page")
            restored = {"edit": await edit.input_value(), "note": await page.input_value("#note")}
            log.append({"restored": restored})
            await page.screenshot(path=str(out / f"{case}-restored.png"))
            async with page.expect_navigation():
                await page.click("button[value=confirm]")
        said = await page.inner_text("body")
        await page.screenshot(path=str(out / f"{case}-after.png"))
        await browser.close()
    view = list_requirements(alice, ListRequirementsInput(brief_id=brief.brief_id))
    answers = sorted(p.name for p in (root / "accounts").rglob("answers/*.signed"))
    result = {
        "case": case,
        "said": said,
        "answers": answers,
        "confirmed": view.model_dump(mode="json"),
        "tokens_minted": state["minted"],
        "log": log,
    }
    (out / f"{case}.json").write_text(json.dumps(result, indent=2))
    shutil.rmtree(root)
    print(json.dumps({k: result[k] for k in ("case", "said", "answers", "tokens_minted")}))
    print(json.dumps(result["confirmed"])[:900])
    print(
        [
            e
            for e in log
            if "status" in e and "127.0.0.1" in str(e["url"]) and "/projects/" in str(e["url"])
        ]
    )
    print([e for e in log if "restored" in e or "console" in e])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(Path(sys.argv[1]), sys.argv[2])))
