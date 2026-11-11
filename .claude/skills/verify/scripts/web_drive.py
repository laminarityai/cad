"""A signed-in person in a real browser on the web app, for `browser.py web ...`.

    uv run python .claude/skills/verify/scripts/browser.py web shot <run> <path> <name> [options]
    uv run python .claude/skills/verify/scripts/browser.py web watch <run> <path> <name> [options]
    uv run python .claude/skills/verify/scripts/browser.py web walk <run> <out> [options]
    uv run python .claude/skills/verify/scripts/browser.py web select <run> <out> [options]
    uv run python .claude/skills/verify/scripts/browser.py web download <run> <out> [options]

<run> is the data root of a local `cad-http` (its `local-issuer.pem` signs the sign-in token),
<path> is a route of the app such as `/projects/<id>`, and <name> is the prefix of the files
written into <run>. Options: --url (the server, default http://127.0.0.1:8765), --account
(default user_web_proof), --width, --height, --scheme (light or dark), --seconds (watch, default
120), --tab (a narrow-screen pane to show: Explorer, Design or Chat).

`shot` opens the page, waits until the option on screen has drawn, and writes <name>.png and
<name>.aria.yml (the page's accessibility tree). `watch` opens the page and polls the check lines
of the option on screen (`[data-line]`, whose value is the line's status) while something else
scores it. It writes <name>-running.png when it first sees a running line, <name>-done.png once
none is left, and <name>.lines.jsonl (every change of a line, and when). It exits 1 when no line
went from running to a verdict, when a running line showed anything but `Checking`, or when the
page navigated after it loaded.

`walk` is one live walk of the project workspace: see web_walk.py. `select` is one live walk of
pointing at a design and asking for a change to it: see web_select.py. `download` is one live walk
of the Download menu and a check of the three files it saves: see web_download.py.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from playwright.sync_api import sync_playwright

from cad.accounts.local import LocalIssuer

if TYPE_CHECKING:
    from playwright.sync_api import Page

COOKIE = "__session"
VERDICTS = {"pass", "fail", "unknown", "researched"}
ARGS = ["--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"]
LINES = """
() => [...document.querySelectorAll("[data-line]")].map((line) => ({
  label: line.querySelector("button > span")?.textContent ?? "", status: line.dataset.line,
  shown: line.querySelector("button > span:last-child")?.textContent ?? "",
}))
"""


def options(argv: list[str]) -> tuple[list[str], dict[str, str]]:
    found = {
        "url": "http://127.0.0.1:8765",
        "account": "user_web_proof",
        "width": "1440",
        "height": "900",
        "scheme": "light",
        "seconds": "120",
        "tab": "",
        "ask": "make the wall 4 mm",
        "video": "",
        "live": "",
        "stop": "button",
        "auto_ask": "Optimise it for me.",
    }
    rest: list[str] = []
    it = iter(argv)
    for word in it:
        if word.startswith("--"):
            found[word[2:]] = next(it)
        else:
            rest.append(word)
    return rest, found


def open_page(playwright: Any, run: Path, path: str, given: dict[str, str]) -> tuple[Any, Page]:
    token = LocalIssuer.open(run / "home", given["url"]).mint_person(given["account"])
    size = {"width": int(given["width"]), "height": int(given["height"])}
    recording: dict[str, Any] = (
        {"record_video_dir": given["video"], "record_video_size": size} if given["video"] else {}
    )
    browser = playwright.chromium.launch(args=ARGS)
    context = browser.new_context(viewport=size, color_scheme=given["scheme"], **recording)
    context.add_cookies([{"name": COOKIE, "value": token, "url": given["url"]}])
    page = context.new_page()
    page.goto(f"{given['url']}/app{path}")
    page.evaluate("window.__alive = true")
    return browser, page


def drawn(page: Page) -> None:
    page.wait_for_selector("[data-slot-tab]", timeout=30_000)
    page.wait_for_function(
        "() => { const v = [...document.querySelectorAll('[data-viewer]')];"
        " return v.length > 0 && v.every((one) => one.querySelector('canvas')); }",
        timeout=60_000,
    )
    page.wait_for_timeout(500)


def open_tab(page: Page, name: str) -> None:
    tab = page.get_by_role("navigation", name="Panes").get_by_role("button", name=name)
    if tab.count():
        tab.click()
        page.wait_for_timeout(300)


def pick_material(page: Page, given: dict[str, str]) -> None:
    if given["tab"]:
        open_tab(page, given["tab"])


def shot(run: Path, path: str, name: str, given: dict[str, str]) -> int:
    with sync_playwright() as playwright:
        browser, page = open_page(playwright, run, path, given)
        drawn(page)
        pick_material(page, given)
        page.screenshot(path=str(run / f"{name}.png"))
        (run / f"{name}.aria.yml").write_text(page.locator("body").aria_snapshot())
        browser.close()
    return 0


def watch(run: Path, path: str, name: str, given: dict[str, str]) -> int:
    started = time.time()
    running: set[str] = set()
    settled: set[str] = set()
    wearing: set[str] = set()
    with sync_playwright() as playwright:
        browser, page = open_page(playwright, run, path, given)
        drawn(page)
        pick_material(page, given)
        navigations: list[str] = []
        page.on("framenavigated", lambda frame: navigations.append(frame.url))
        last: dict[str, str] = {}
        with (run / f"{name}.lines.jsonl").open("w") as log:
            while time.time() - started < float(given["seconds"]):
                lines: list[dict[str, str]] = page.evaluate(LINES)
                for line in lines:
                    label, status = line["label"], line["status"]
                    if last.get(label) != status:
                        log.write(json.dumps({"at": time.time(), **line}) + "\n")
                        log.flush()
                    if status == "running" and not running:
                        page.screenshot(path=str(run / f"{name}-running.png"))
                    if status == "running":
                        running.add(label)
                        if line["shown"] != "Checking":
                            wearing.add(label)
                    elif label in running and status in VERDICTS:
                        settled.add(label)
                    last[label] = status
                if running and lines and all(one["status"] != "running" for one in lines):
                    page.wait_for_timeout(400)
                    page.screenshot(path=str(run / f"{name}-done.png"))
                    break
                page.wait_for_timeout(250)
        (run / f"{name}.aria.yml").write_text(page.locator("body").aria_snapshot())
        browser.close()
    print(
        json.dumps(
            {
                "running_lines_seen": sorted(running),
                "settled_to_a_verdict": sorted(settled),
                "running_lines_showing_a_verdict": sorted(wearing),
                "navigations_after_load": navigations,
            }
        )
    )
    return 0 if settled and not wearing and not navigations else 1


def main(argv: list[str]) -> int:
    rest, given = options(argv)
    match rest:
        case ["shot", run, path, name]:
            return shot(Path(run), path, name, given)
        case ["watch", run, path, name]:
            return watch(Path(run), path, name, given)
        case ["walk", *_]:
            from web_walk import main as walk

            return walk(argv[1:])
        case ["download", *_]:
            from web_download import main as download

            return download(argv[1:])
        case ["select", *_]:
            from web_select import main as select

            return select(argv[1:])
        case _:
            print(__doc__)
            return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
