"""Run briefs through the in-process chat agent, as the web app does, and stop at the Auto stop.

    uv run python evals/briefs/run.py --driver inprocess --briefs ~/cad-evals/briefs --out <dir>
        [--model scripted|<anthropic model id>] [--only ID ...] [--opener PROGRAM] [--timeout S]

Briefs run one after another: each has its own home under `<out>/<id>/home`, and the
sandbox is shared. `<out>/<id>/auto.json` holds the result and `events.json` the transcript.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import httpx2
from autoresult import EVENTS, AutoResult, Expect, judge, summary_line, write_result
from autoscript import script_for
from brief_set import BriefInput, prompt_for
from friction import read_pages

from cad.accounts.local import LocalIssuer
from cad.accounts.meter import USAGE, parse_lines
from cad.accounts.principal import AccountId
from cad.auto import log
from cad.auto.model import NeedsPerson, Stopped
from cad.chat.anthropic_model import KEY_VARIABLE, AnthropicModel
from cad.chat.model import Model
from cad.chat.scripted import Scripted
from cad.confirmations.waiting import WAIT_SECONDS, Door, Opener, PageUrl, program_opener
from cad.confirmations.web import LocalSignIn
from cad.context_parts.ingest import ingest
from cad.conversations import store
from cad.conversations.model import ConversationId
from cad.operations.tenants import ACCOUNTS, Tenants
from cad.server.app import LocalPage
from cad.server.hosted import DAILY_CAP_SECONDS, build_app

SCRIPTED: Final = "scripted"
ACCOUNT: Final = "user_eval"
BASE: Final = "http://127.0.0.1:8765"
JSON: Final = {"Content-Type": "application/json"}
HUMAN: Final = Path(__file__).resolve().parents[2] / ".claude/skills/verify/scripts/human.py"
HUMAN_LOG: Final = "human.jsonl"
PERSON_ENV: Final = ("PATH", "HOME", "LANG", "LC_ALL", "CAD_HUMAN_DELAY")
TURN_TIMEOUT_S: Final = 900.0


class MissingKey(Exception):
    pass


def require_key(model: str, environ: Mapping[str, str]) -> None:
    """A live model needs its key, and a run says so before anything starts."""
    if model != SCRIPTED and not environ.get(KEY_VARIABLE, "").strip():
        raise MissingKey(f"{KEY_VARIABLE} is not set, so the live model {model} cannot run")


def model_for(name: str, brief: BriefInput) -> Model:
    if name == SCRIPTED:
        return Scripted(script_for(brief), Path.cwd())
    return AnthropicModel(name, os.environ)


def scripted_person(log_path: Path) -> Opener:
    """The same scripted person the stdio brief set uses: `human.py` answers the page."""
    environ = {k: os.environ[k] for k in PERSON_ENV if k in os.environ}
    environ["CAD_HUMAN_LOG"] = str(log_path)

    def open_page(url: PageUrl) -> None:
        child = subprocess.Popen(
            [sys.executable, str(HUMAN), url],
            env=environ,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        threading.Thread(target=child.wait, daemon=True).start()

    return open_page


def parse_stream(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        fields = dict(row.split(": ", 1) for row in block.splitlines() if ": " in row)
        if "data" in fields:
            found.append({"seq": int(fields["id"]), **json.loads(fields["data"])})
    return found


def container_runs(base: Path) -> int:
    """Each sandbox container charges the account's meter with a `reserve` line."""
    lines = [
        line
        for day in sorted((base / USAGE).glob("*.jsonl"))
        for line in parse_lines(day.read_bytes())
    ]
    return sum(one.op == "reserve" for one in lines)


def variant_count(base: Path) -> int:
    variants = base / "variants"
    return sum(one.is_dir() for one in variants.iterdir()) if variants.is_dir() else 0


async def converse(
    brief: BriefInput, model: Model, local: LocalIssuer, tenants: Tenants, timeout_s: float
) -> list[dict[str, Any]]:
    app = build_app(local.issuer(), tenants, LocalSignIn(local), model)
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url=BASE) as client:
            client.cookies.set("__session", local.mint_person(ACCOUNT))
            made = await client.post("/v1/conversations", headers=JSON, content=b"{}")
            cid = made.json()["conversation_id"]
            body = json.dumps({"text": prompt_for(brief)})
            sent = await client.post(
                f"/v1/conversations/{cid}/messages", headers=JSON, content=body
            )
            if sent.status_code != 202:
                raise RuntimeError(f"the message was refused: {sent.text}")
            await asyncio.wait_for(app.state.chat.idle(), timeout_s)
            streamed = await client.get(f"/v1/conversations/{cid}/stream?follow=false")
    return [{"conversation_id": cid}, *parse_stream(streamed.text)]


def run_brief(
    brief: BriefInput, out: Path, name: str, opener_program: str | None, timeout_s: float
) -> AutoResult:
    directory = out / brief.id
    if directory.exists():
        shutil.rmtree(directory)
    home = directory / "home"
    home.mkdir(parents=True)
    human_log = directory / HUMAN_LOG
    opener = program_opener(opener_program) if opener_program else scripted_person(human_log)
    local = LocalIssuer.open(home, BASE)
    page = LocalPage(opener, lambda: tenants.of(AccountId(ACCOUNT)))
    door = Door(open_page=page.open, wait_seconds=WAIT_SECONDS)
    tenants = Tenants(home / ACCOUNTS, DAILY_CAP_SECONDS, door, ingest)
    started = time.monotonic()
    try:
        events = asyncio.run(converse(brief, model_for(name, brief), local, tenants, timeout_s))
        error = None
    except (TimeoutError, RuntimeError, OSError) as failure:
        events, error = [], f"{type(failure).__name__}: {failure}"
    seconds = time.monotonic() - started
    (directory / EVENTS).write_text(json.dumps(events, indent=2) + "\n")
    result = read_result(brief, name, events, error, tenants, human_log, seconds)
    write_result(out, result)
    return result


def read_result(
    brief: BriefInput,
    name: str,
    events: list[dict[str, Any]],
    error: str | None,
    tenants: Tenants,
    human_log: Path,
    seconds: float,
) -> AutoResult:
    tenant = tenants.of(AccountId(ACCOUNT))
    base = tenants.accounts / ACCOUNT
    failures = [str(one["message"]) for one in events if one.get("kind") == "turn_failed"]
    problems = [*([error] if error else []), *failures]
    report = next((one for one in events if one.get("kind") == "stop_report"), None)
    stop: str | None = None
    text, builds, bounds = "", 0, ()
    if report is not None:
        run = log.read_run(tenant.roots, report["run_id"])
        assert isinstance(run.state, Stopped)
        reason = run.state.reason
        stop = reason.why if isinstance(reason, NeedsPerson) else reason.kind
        text, builds = run.state.report, len(run.state.builds)
        bounds = reason.bounds if isinstance(reason, NeedsPerson) else ()
    stopped_run = None
    if events:
        cid = ConversationId(events[0]["conversation_id"])
        stopped_run = store.read(tenant.conversations, cid).stopped_run
    judged = judge(Expect.of(brief.grader), name != SCRIPTED, stop, text, builds, bounds)
    return AutoResult(
        id=brief.id,
        domain=brief.domain,
        model=name,
        status="failed" if problems else ("stopped" if report is not None else "not_stopped"),
        run_id=None if report is None else report["run_id"],
        stop=stop,
        bounds=bounds,
        report=text,
        builds=builds,
        stopped_run=stopped_run,
        variants=variant_count(base),
        containers=container_runs(base),
        pages=read_pages(human_log).shown,
        tool_errors=sum(
            1 for one in events if one.get("kind") == "tool_result" and one["is_error"]
        ),
        seconds=seconds,
        problems=(*problems, *judged),
    )


def run_set(
    briefs: Sequence[BriefInput],
    out: Path,
    name: str,
    opener_program: str | None,
    timeout_s: float,
) -> list[AutoResult]:
    """One brief after another. Returns every result, and prints one line for each."""
    results: list[AutoResult] = []
    for brief in briefs:
        result = run_brief(brief, out, name, opener_program, timeout_s)
        print(summary_line(result), flush=True)
        results.append(result)
    return results
