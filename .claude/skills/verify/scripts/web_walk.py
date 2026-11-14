"""One live walk of the project workspace, the way a person uses it.

    uv run python .claude/skills/verify/scripts/browser.py web walk <run> <out> [--url URL]
        [--account ID] [--brief TEXT] [--change TEXT] [--lid TEXT]

<run> is the data root of a running local `cad-http` (its `local-issuer.pem` signs the sign-in
token) and <out> the folder the screenshots go to. The walk starts on the empty `/app`, types the
brief, skips the questions card when the agent asks first, waits for the options, confirms the chat
card when the brief states a target, asks for a change and steps back to the earlier revision,
asks for a lid, waits for its options, confirms its card when there is one, and turns the fit
ghost on. It shoots each step in dark mode at 1440 px, and the lid's workspace at 400 px, and
exits 1 at the first step that did not happen, naming it.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import sync_playwright

from cad.accounts.local import LocalIssuer

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

ARGS = ["--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"]
AGENT_SECONDS = 600
DEFAULTS = {
    "url": "http://127.0.0.1:8765",
    "account": "user_walk",
    "brief": "An open box for my desk, 60 by 40 by 30 mm outside, with 2 mm walls.",
    "change": "Give option 1 rounded outside corners.",
    "lid": "Now a lid for that box. It should plug into the top and fit with about 0.3 mm gap.",
}


MISSED_SHOT: list[Path] = [Path("missed.png")]


class Missed(Exception):
    pass


def options(argv: list[str]) -> tuple[list[str], dict[str, str]]:
    found = dict(DEFAULTS)
    rest: list[str] = []
    it = iter(argv)
    for word in it:
        if word.startswith("--"):
            found[word[2:]] = next(it)
        else:
            rest.append(word)
    return rest, found


def page_for(browser: Browser, run: Path, given: dict[str, str], width: int) -> Page:
    token = LocalIssuer.open(run / "home", given["url"]).mint_person(given["account"])
    context = browser.new_context(viewport={"width": width, "height": 900}, color_scheme="dark")
    context.add_cookies([{"name": "__session", "value": token, "url": given["url"]}])
    return context.new_page()


SEND_TRIES = 6


def step(name: str, page: Page, check: str, seconds: int = AGENT_SECONDS) -> None:
    started = time.monotonic()
    try:
        page.wait_for_function(check, timeout=seconds * 1000)
    except Exception as error:
        page.screenshot(path=str(MISSED_SHOT[0]))
        raise Missed(f"{name}: {check} did not hold within {seconds} s") from error
    print(f"{name}: {time.monotonic() - started:.0f} s", flush=True)


def idle(page: Page) -> None:
    quiet = "() => !document.querySelector('section[aria-label=Chat][aria-busy=true]')"
    for _ in range(3):
        page.wait_for_timeout(1000)
        step("idle", page, quiet)


def say(page: Page, text: str) -> None:
    """The page can show the turn as ended a moment before the server takes a new message, so a
    message the server turned away is sent again."""
    sent = "() => document.querySelector('textarea').value === ''"
    box = page.get_by_label("Message")
    for _ in range(SEND_TRIES - 1):
        idle(page)
        box.fill(text)
        box.press("Enter")
        try:
            page.wait_for_function(sent, timeout=10_000)
        except Exception:
            page.wait_for_timeout(10_000)
            continue
        print("sent", flush=True)
        return
    idle(page)
    box.fill(text)
    box.press("Enter")
    step("sent", page, sent, 30)


def shoot(page: Page, out: Path, name: str) -> None:
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / f"{name}.png"))
    print(f"shot {name}.png", flush=True)


CARD = "[data-confirm-card] [data-confirm]"


def confirm(page: Page) -> None:
    step("card", page, f"() => document.querySelector({CARD!r})")
    page.locator(CARD).click()
    step("card answered", page, "() => !document.querySelector('[data-confirm-card]')", 60)


def confirm_if_asked(page: Page, out: Path, name: str) -> bool:
    """A brief that states no number shows no card, so a missing card is not a miss. The options
    stand before the card shows, and the click rebuilds nothing."""
    if not page.locator(CARD).count():
        print("no card", flush=True)
        return False
    shoot(page, out, name)
    confirm(page)
    return True


QUESTIONS = "[data-questions]"


def skip_if_asked(page: Page, out: Path, name: str) -> bool:
    """The agent may ask a few questions before the first build. They show on /app, before the
    page moves to the project, and Skip builds with the agent's defaults."""
    asked_or_built = (
        f"() => location.pathname.includes('/projects/') || document.querySelector({QUESTIONS!r})"
    )
    step("asked or built", page, asked_or_built)
    if not page.locator(QUESTIONS).count():
        print("no questions", flush=True)
        return False
    shoot(page, out, name)
    page.locator(QUESTIONS).get_by_role("button", name="Skip").click()
    return True


def walk(run: Path, out: Path, given: dict[str, str]) -> None:
    drawn = "() => document.querySelector('[data-stage] canvas')"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=ARGS)
        page = page_for(browser, run, given, 1440)
        page.goto(f"{given['url']}/app")
        step("chat start", page, "() => document.querySelector('textarea')", 30)
        shoot(page, out, "walk-1-start")
        say(page, given["brief"])
        skip_if_asked(page, out, "walk-1b-questions")
        step("project page", page, "() => location.pathname.includes('/projects/')")
        step("options", page, "() => document.querySelectorAll('[data-slot-tab]').length > 0")
        step("drawn", page, drawn)
        idle(page)
        rows = "[data-line], [data-awaiting] li"
        step("checked", page, f"() => document.querySelectorAll({rows!r}).length > 0", 300)
        shoot(page, out, "walk-2-options")
        if confirm_if_asked(page, out, "walk-3-confirm-in-chat"):
            step("judged", page, "() => document.querySelectorAll('[data-line]').length > 0", 120)
            idle(page)
            shoot(page, out, "walk-3b-judged")
        say(page, given["change"])
        page.wait_for_timeout(3000)
        idle(page)
        confirm_if_asked(page, out, "walk-4a-change-confirm")
        step(
            "revision 2",
            page,
            "() => /of [2-9]/.test(document.querySelector('[data-revisions]')?.innerText ?? '')",
        )
        idle(page)
        page.get_by_label("Earlier revision").click()
        step(
            "stepped back",
            page,
            "() => /Revision 1 of/.test(document.querySelector('[data-revisions]').innerText)",
            30,
        )
        shoot(page, out, "walk-4-earlier-revision")
        say(page, given["lid"])
        step(
            "lid built",
            page,
            "() => document.querySelector('[data-confirm-card], [data-fit-toggle]')",
        )
        idle(page)
        confirm_if_asked(page, out, "walk-5-lid-confirm")
        step("fit toggle", page, "() => document.querySelector('[data-fit-toggle]')")
        step("lid drawn", page, drawn)
        idle(page)
        step(
            "lid checked",
            page,
            "() => !/Checking/.test(document.querySelector('section[aria-label=Checks]')"
            "?.innerText ?? 'Checking')",
        )
        toggle = page.locator("[data-fit-toggle]")
        if toggle.get_attribute("aria-pressed") != "true":
            toggle.click()
        shoot(page, out, "walk-6-fit-ghost")
        narrow = page_for(browser, run, given, 400)
        narrow.goto(page.url)
        step("narrow drawn", narrow, drawn, 60)
        shoot(narrow, out, "walk-7-narrow")
        browser.close()


def main(argv: list[str]) -> int:
    rest, given = options(argv)
    if len(rest) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    run, out = Path(rest[0]), Path(rest[1])
    out.mkdir(parents=True, exist_ok=True)
    MISSED_SHOT[0] = out / "missed.png"
    try:
        walk(run, out, given)
    except Missed as missed:
        print(f"missed {missed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
