"""A person in a real browser on the confirmation page, with one Chromium for a whole run.

    uv run python .claude/skills/verify/scripts/browser.py start <dir>    once per run
    <dir>/bin/open <url>                                                   the opener
    uv run python .claude/skills/verify/scripts/browser.py set <dir> [answer=.] [edit=.] [delay=.]
    uv run python .claude/skills/verify/scripts/browser.py status <dir>
    uv run python .claude/skills/verify/scripts/browser.py stop <dir>
    uv run python .claude/skills/verify/scripts/browser.py web shot|watch <run> <path> <name>
        (see web_drive.py)

`start` launches one headless Chromium behind a daemon on 127.0.0.1 and returns once it answers.
It writes `<dir>/bin/open`, which hands a page URL to that daemon, so pass it as
`cad-server --opener`, or put `<dir>/bin` first on PATH for `cad-call`, whose server runs `open`.
Each page gets its own browser context, a page number n, `<dir>/page-<n>.aria.yml`,
`<dir>/page-<n>-before.png` (just before the click) and `<dir>/page-<n>-after.png` (the reply),
and JSON lines in `<dir>/browser.jsonl`. How the person answers is answer (confirm or decline),
edit ("<shown>=<typed>": type <typed> into each Change to field whose placeholder is <shown>) and
delay (seconds before answering). `set` changes them for every later page. CAD_HUMAN_ANSWER,
CAD_HUMAN_EDIT and CAD_HUMAN_DELAY in the opener's environment override them for one page, but
`cad-call`'s server never sees those variables, so use `set` there.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from playwright.async_api import Browser, Page

type Entry = dict[str, object]
FROM = "From your words: "
NOTE_LABEL = "Note to the agent, if you decline"
BUTTON = {"confirm": "Confirm", "decline": "Decline all"}


PERSON = ("answer", "edit", "delay")


@dataclass(frozen=True, slots=True)
class Visit:
    url: str
    answer: Literal["confirm", "decline"]
    edit: tuple[str, str] | None
    delay: float


def visit_of(url: str, person: dict[str, str]) -> Visit:
    answer = person["answer"]
    if answer != "confirm" and answer != "decline":
        raise ValueError(f"answer must be confirm or decline, not {answer!r}")
    shown, _, typed = person["edit"].partition("=")
    return Visit(url, answer, (shown, typed) if shown else None, float(person["delay"]))


def ask(run: Path, request: Entry, timeout: float = 5) -> Entry | None:
    """Send one request to the daemon of `run`. None when no daemon answers there."""
    try:
        port = int((run / "browser.port").read_text())
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as connection:
            connection.sendall(json.dumps(request).encode() + b"\n")
            reply: Entry = json.loads(connection.makefile().readline())
            return reply
    except (OSError, ValueError):
        return None


def append(run: Path, entry: Entry) -> None:
    with (run / "browser.jsonl").open("a") as file:
        file.write(json.dumps(entry) + "\n")


def start(run: Path) -> int:
    run.mkdir(parents=True, exist_ok=True)
    run = run.resolve()
    running = ask(run, {"do": "status"})
    if running is not None:
        print(f"browser already running: {json.dumps(running)}")
        return 0
    shim = run / "bin" / "open"
    shim.parent.mkdir(exist_ok=True)
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), "open", str(run)])
    shim.write_text(f'#!/bin/sh\nexec {command} "$1"\n')
    shim.chmod(0o755)
    (run / "browser.port").unlink(missing_ok=True)
    with (run / "browser.log").open("a") as log:
        daemon = subprocess.Popen(
            [sys.executable, __file__, "serve", str(run)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status = ask(run, {"do": "status"})
        if status is not None:
            print(f"browser ready: {json.dumps(status)}")
            print(f"opener: {shim}")
            return 0
        if daemon.poll() is not None:
            print(f"browser daemon exited {daemon.returncode}; see {run / 'browser.log'}")
            return 1
        time.sleep(0.1)
    print(f"browser daemon {daemon.pid} did not answer in 60 s; see {run / 'browser.log'}")
    return 1


def open_page(run: Path, url: str) -> int:
    given = {k: v for k in PERSON if (v := os.environ.get(f"CAD_HUMAN_{k.upper()}")) is not None}
    request: Entry = {"do": "visit", "url": url, "person": given}
    reply = ask(run, request, timeout=120)
    if reply is None:
        append(run, {"error": f"no browser daemon answered in {run}; run browser.py start"})
        return 1
    if "error" in reply:
        print(reply["error"], file=sys.stderr)
        return 1
    return 0


def last_page(run: Path) -> int:
    """The highest page number any file or log line of `run` already uses, 0 when none."""
    used = [int(m[1]) for f in run.glob("page-*") if (m := re.match(r"page-(\d+)[.-]", f.name))]
    log = run / "browser.jsonl"
    for line in log.read_text().splitlines() if log.exists() else []:
        try:
            entry: Entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(page := entry.get("page"), int):
            used.append(page)
    return max(used, default=0)


def stop(run: Path) -> int:
    reply = ask(run, {"do": "stop"})
    if reply is None:
        print(f"no browser running for {run}")
        return 0
    pid = int(str(reply["pid"]))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            print(f"browser stopped: pid {pid}, {reply['pages']} pages")
            return 0
        time.sleep(0.1)
    print(f"browser daemon {pid} is still running; stop it with: kill {pid}")
    return 1


async def serve(run: Path) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        numbers = itertools.count(1 + last_page(run))
        served: list[int] = []
        person = {"answer": "confirm", "edit": "", "delay": "1"}
        stopping = asyncio.Event()

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            reply: Entry = {"pid": os.getpid(), "browser": browser.version, "pages": len(served)}
            try:
                request = cast(Entry, json.loads(await reader.readline()))
                action = request["do"]
                given = cast(Entry, request.get("person") or {})
                changes = {str(k): str(v) for k, v in given.items()}
                if unknown := sorted(set(changes) - set(PERSON)):
                    raise ValueError(f"unknown setting {unknown}; the settings are {list(PERSON)}")
                if action == "stop":
                    stopping.set()
                elif action == "set":
                    visit_of("", person | changes)
                    person.update(changes)
                    append(run, {"step": "set", **person})
                elif action == "visit":
                    visit = visit_of(str(request["url"]), person | changes)
                    n = next(numbers)
                    failure = await drive(browser, run, n, visit)
                    reply["page"] = n
                    if failure is None:
                        served.append(n)
                    else:
                        reply["error"] = failure
                elif action != "status":
                    raise ValueError(f"unknown request {action!r}")
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                reply["error"] = f"bad request: {type(error).__name__}: {error}"
                append(run, {"error": reply["error"]})
            reply["person"] = person
            writer.write(json.dumps(reply).encode() + b"\n")
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        (run / "browser.pid").write_text(str(os.getpid()))
        (run / "browser.port").write_text(str(port))
        async with server:
            await stopping.wait()
        await browser.close()
    (run / "browser.port").unlink(missing_ok=True)
    (run / "browser.pid").unlink(missing_ok=True)


async def drive(browser: Browser, run: Path, n: int, visit: Visit) -> str | None:
    """Drive one page. None on success, else the failure, with the page token left out."""
    token = urlsplit(visit.url).path.rpartition("/")[2]

    def log(entry: Entry) -> None:
        append(run, {"page": n, **entry})

    context = await browser.new_context(viewport={"width": 900, "height": 900})
    context.set_default_timeout(10_000)
    try:
        page = await context.new_page()
        opened = await page.goto(visit.url)
        status = opened.status if opened else None
        sections = await read_sections(page)
        aria = run / f"page-{n}.aria.yml"
        aria.write_text(await page.locator("body").aria_snapshot())
        heading = page.get_by_role("heading", level=1)
        log(
            {
                "step": "page",
                "status": status,
                "heading": await heading.inner_text() if await heading.count() else None,
                "sections": sections,
                "quotes_in_brief": bool(sections) and all(s["quotes_in_brief"] for s in sections),
                "aria": aria.name,
            }
        )
        if status != 200:
            await page.screenshot(path=run / f"page-{n}-before.png", full_page=True)
            return None
        await asyncio.sleep(visit.delay)
        if visit.edit is not None:
            shown, typed = visit.edit
            fields = page.get_by_role("textbox", name="Change to").and_(
                page.get_by_placeholder(shown, exact=True)
            )
            for field in await fields.all():
                await field.fill(typed)
            log({"step": "edit", "shown": shown, "typed": typed, "fields": await fields.count()})
        if visit.answer == "decline":
            await page.get_by_label(NOTE_LABEL).fill("scripted person declined")
        await page.screenshot(path=run / f"page-{n}-before.png", full_page=True)
        button = page.get_by_role("button", name=BUTTON[visit.answer], exact=True)
        async with page.expect_response(lambda r: r.request.method == "POST") as posted:
            await button.click()
        answered = await posted.value
        await page.wait_for_load_state()
        said = await page.locator("body").inner_text()
        await page.screenshot(path=run / f"page-{n}-after.png", full_page=True)
        log({"step": visit.answer, "status": answered.status, "said": said})
        log({"spent_token": token})
    except Exception as error:  # the server discards the opener's output, so log every failure
        failure = f"{type(error).__name__}: {error}"
        failure = failure.replace(token, "<token>") if token else failure
        log({"error": failure})
        return failure
    finally:
        await context.close()
    return None


async def read_sections(page: Page) -> list[dict[str, object]]:
    """Each section by its h2: the brief in its blockquote, and the quote under each requirement."""
    found: list[dict[str, object]] = []
    sections = page.locator("section").filter(has=page.get_by_role("heading", level=2))
    for section in await sections.all():
        brief = await section.get_by_role("blockquote").inner_text()
        rows = [await row.inner_text() for row in await section.get_by_role("listitem").all()]
        quotes = [
            line.removeprefix(FROM)
            for row in rows
            for line in row.splitlines()
            if line.startswith(FROM)
        ]
        found.append(
            {
                "heading": await section.get_by_role("heading", level=2).inner_text(),
                "brief": brief,
                "quotes": quotes,
                "quotes_in_brief": bool(quotes) and all(quote in brief for quote in quotes),
            }
        )
    return found


def main(argv: list[str]) -> int:
    match argv:
        case ["start", run]:
            return start(Path(run))
        case ["serve", run]:
            asyncio.run(serve(Path(run)))
            return 0
        case ["open", run, url]:
            return open_page(Path(run), url)
        case ["set", run, *pairs] if all("=" in pair for pair in pairs):
            given = {key: value for key, _, value in (pair.partition("=") for pair in pairs)}
            reply = ask(Path(run), {"do": "set", "person": given})
            print(json.dumps(reply) if reply else f"no browser running for {run}")
            return 0 if reply and "error" not in reply else 1
        case ["status", run]:
            reply = ask(Path(run), {"do": "status"})
            print(json.dumps(reply) if reply else f"no browser running for {run}")
            return 0 if reply else 1
        case ["stop", run]:
            return stop(Path(run))
        case ["web", *rest]:
            import web_drive

            return web_drive.main(rest)
        case _:
            print(__doc__)
            return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
