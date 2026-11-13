"""Record the landing page's pictures from one real brief. One command, rerunnable.

    uv run python tools/landing_capture.py --dry     # a scripted model, no money
    uv run python tools/landing_capture.py           # one live session, the spend guard on

It starts `cad-http` on a scratch HOME and its own port, types the brief in
`web/src/features/landing/capture.json` into the web app, waits for the options and their checks,
shoots the stills, confirms the targets, shoots the judged scorecard, and cuts a short silent loop
from the recordings. A light browser drives the session and a dark one follows it, so every
picture exists in both themes from one model session. It writes the files into
`web/src/features/landing/assets/` with a `manifest.json` of their sizes.

The live run needs Docker for the sandbox and a key in `~/.config/cad/anthropic.env`, which this
script reads only to hand it to the server. Nothing it writes may show an email address or a local
path, and it checks the page text for both before each shot. The spend guard stops the server and
the script when the model usage lines of the server's log add up to more than `--budget` USD.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import landing_media as media
from landing_server import Missed, Server, preflight, say
from landing_video import cut, poster, to_webp
from playwright.sync_api import ViewportSize, sync_playwright

from cad.accounts.local import LocalIssuer

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page

ROOT: Final = Path(__file__).resolve().parents[1]
LANDING: Final = ROOT / "web" / "src" / "features" / "landing"
ASSETS: Final = LANDING / "assets"
ARGS: Final = ["--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"]
DESKTOP: Final = ViewportSize(width=1280, height=800)
PHONE: Final = ViewportSize(width=390, height=844)
AGENT_SECONDS: Final = 900
THEMES: Final = ("light", "dark")
SCHEMES: Final[dict[str, Any]] = {"light": "light", "dark": "dark"}


def person(
    server: Server, browser: Browser, scheme: str, size: ViewportSize, video: Path | None
) -> BrowserContext:
    token = LocalIssuer.open(server.data / "home", server.url).mint_person("demo")
    recording: dict[str, Any] = (
        {"record_video_dir": str(video), "record_video_size": size} if video else {}
    )
    context = browser.new_context(viewport=size, color_scheme=SCHEMES[scheme], **recording)
    context.add_cookies([{"name": "__session", "value": token, "url": server.url}])
    return context


def wait(page: Page, name: str, check: str, seconds: int = AGENT_SECONDS) -> float:
    started = time.monotonic()
    try:
        page.wait_for_function(check, timeout=seconds * 1000)
    except Exception as error:
        raise Missed(f"{name}: {check} did not hold within {seconds} s") from error
    say(f"{name}: {time.monotonic() - started:.0f} s")
    return time.monotonic()


def idle(page: Page) -> None:
    quiet = "() => !document.querySelector('section[aria-label=Chat][aria-busy=true]')"
    for _ in range(3):
        page.wait_for_timeout(1000)
        wait(page, "idle", quiet)


CARD = "[data-confirm-card] [data-confirm]"
OPTIONS = "() => document.querySelectorAll('[data-slot-tab]').length > 0"
DRAWN = "() => !!document.querySelector('[data-stage] canvas')"
LINES = "() => document.querySelectorAll('[data-line], [data-awaiting] li').length > 0"
NONE_RUNNING = (
    "() => ![...document.querySelectorAll('[data-line]')]"
    ".some((one) => one.dataset.line === 'running')"
)
MOMENTS = (("options", OPTIONS), ("drawn", DRAWN), ("lines", LINES), ("done", NONE_RUNNING))
JUDGED = (
    "() => document.querySelectorAll('[data-line]').length > 0"
    " && !document.querySelector('[data-confirm-card]')"
)


def clean(page: Page, home: str) -> None:
    """Stop at a page that shows an email address or a local path, before any picture is taken."""
    found = media.leaks(page.locator("body").inner_text(), home)
    if found:
        raise Missed(f"the page shows {found}, so no picture was taken")


def expand(page: Page) -> None:
    """Open the first two check lines, so the picture shows the formula and its source."""
    for number in range(min(2, page.locator("[data-line]").count())):
        trigger = page.locator("[data-line]").nth(number).locator("button").first
        if trigger.get_attribute("aria-expanded") != "true":
            trigger.click()
    page.wait_for_timeout(400)


def checks(page: Page) -> Any:
    return page.locator("section[aria-label=Checks]")


def still(page: Page, work: Path, home: str, name: str, element: Any = None) -> Path:
    clean(page, home)
    page.wait_for_timeout(1200)
    target = work / f"{name}.png"
    (element if element is not None else page).screenshot(path=str(target))
    say(f"shot {target.name}")
    return target


def watch(pages: dict[str, Page], starts: dict[str, float]) -> dict[str, dict[str, float]]:
    """Seconds from the start of each page's recording to each moment the loop is cut from.

    Both pages are polled in one loop, because a recording of the dark page that is read after
    the light one has finished would find every moment already past.
    """
    marks: dict[str, dict[str, float]] = {theme: {} for theme in pages}
    deadline = time.monotonic() + AGENT_SECONDS
    while any(len(one) < len(MOMENTS) for one in marks.values()):
        if time.monotonic() > deadline:
            raise Missed(f"the checks did not finish in {AGENT_SECONDS} s: {marks}")
        for theme, page in pages.items():
            name, check = (
                MOMENTS[len(marks[theme])] if len(marks[theme]) < len(MOMENTS) else ("", "")
            )
            if name and page.evaluate(f"({check})()"):
                marks[theme][name] = time.monotonic() - starts[theme]
                say(f"{theme} {name} at {marks[theme][name]:.0f} s")
        time.sleep(0.25)
    return marks


def stop_auto(page: Page) -> None:
    """A live agent can start an Auto run. The capture ends it, so the session spends no more."""
    stop = page.get_by_role("button", name="Stop")
    if stop.count() and stop.first.is_visible():
        stop.first.click()
        say("stopped an Auto run")


def session(
    server: Server, work: Path, out: Path, crf: int, quality: int
) -> dict[str, tuple[int, int]]:
    sizes: dict[str, tuple[int, int]] = {}
    brief = json.loads((LANDING / "capture.json").read_text())["brief"]
    home = str(server.home)
    videos = work / "video"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=ARGS)
        drive_start = time.monotonic()
        driver = person(server, browser, "light", DESKTOP, videos / "light")
        page = driver.new_page()
        page.goto(f"{server.url}/app")
        wait(page, "chat start", "() => document.querySelector('textarea')", 60)
        page.get_by_label("Message").fill(brief)
        page.get_by_label("Message").press("Enter")
        wait(page, "project page", "() => location.pathname.includes('/projects/')", 120)
        follow_start = time.monotonic()
        follower = person(server, browser, "dark", DESKTOP, videos / "dark")
        dark = follower.new_page()
        dark.goto(page.url)
        pages = {"light": page, "dark": dark}
        marks = watch(pages, {"light": drive_start, "dark": follow_start})
        for one in pages.values():
            idle(one)
        for theme, one in pages.items():
            sizes[f"options-{theme}.webp"] = to_webp(
                still(one, work, home, f"options-{theme}"), out / f"options-{theme}.webp", quality
            )
            sizes[f"waiting-{theme}.webp"] = to_webp(
                still(one, work, home, f"waiting-{theme}", checks(one)),
                out / f"waiting-{theme}.webp",
                quality,
            )
        for theme in THEMES:
            narrow = person(server, browser, theme, PHONE, None)
            small = narrow.new_page()
            small.goto(page.url)
            wait(small, "narrow drawn", DRAWN, 120)
            sizes[f"options-{theme}-narrow.webp"] = to_webp(
                still(small, work, home, f"options-{theme}-narrow"),
                out / f"options-{theme}-narrow.webp",
                quality,
            )
            narrow.close()
        wait(page, "card", f"() => document.querySelector({CARD!r})", 120)
        page.locator(CARD).click()
        wait(page, "judged", JUDGED, 300)
        idle(page)
        stop_auto(page)
        dark.reload()
        wait(dark, "dark judged", JUDGED, 120)
        for theme, one in pages.items():
            wait(one, "drawn", DRAWN, 120)
            expand(one)
            sizes[f"scorecard-{theme}.webp"] = to_webp(
                still(one, work, home, f"scorecard-{theme}", checks(one)),
                out / f"scorecard-{theme}.webp",
                quality,
            )
        driver.close()
        follower.close()
        browser.close()
    for theme in THEMES:
        recording = next((videos / theme).glob("*.webm"))
        file = out / f"hero-{theme}.webm"
        sizes[file.name] = cut(recording, marks[theme], file, crf)
        poster(file, out / f"hero-poster-{theme}.webp", work)
        sizes[f"hero-poster-{theme}.webp"] = sizes[file.name]
    return sizes


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--dry", action="store_true", help="a scripted model, no key and no money")
    parser.add_argument(
        "--budget", type=float, default=1.6, help="stop the server above this many USD"
    )
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--crf", type=int, default=42, help="video quality, higher is smaller")
    parser.add_argument("--quality", type=int, default=78, help="webp quality")
    parser.add_argument(
        "--work", type=Path, default=None, help="scratch folder, default a new temp one"
    )
    given = parser.parse_args(argv)
    work = given.work or Path(tempfile.mkdtemp(prefix="landing-capture-"))
    work.mkdir(parents=True, exist_ok=True)
    out = work / "out"
    out.mkdir(exist_ok=True)
    server: Server | None = None
    try:
        preflight(given.dry, given.port)
        server = Server(work, given.port, given.dry, given.budget)
        server.wait_ready()
        sizes = session(server, work, out, given.crf, given.quality)
        weight = media.write_manifest(out, sizes)
        say(f"files weigh {weight} bytes; the model cost about {server.spent():.2f} USD (estimate)")
        if media.over_budget(weight):
            raise Missed(
                f"the pictures weigh {weight} bytes, over {media.BUDGET_BYTES}."
                " Raise --crf or lower --quality."
            )
        for old in ASSETS.iterdir():
            old.unlink()
        for new in out.iterdir():
            shutil.copy2(new, ASSETS / new.name)
        say(f"wrote {len(sizes)} files to {ASSETS}")
    except Missed as missed:
        print(f"missed: {missed}", file=sys.stderr)
        return 1
    finally:
        if server is not None:
            if server.over.is_set():
                print("the spend guard stopped the server", file=sys.stderr)
            server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
