"""One live walk of pointing at a design and asking for a change to what is pointed at.

    uv run python .claude/skills/verify/scripts/browser.py web select <run> <out> [--url URL]
        [--account ID] [--brief TEXT] [--thicker TEXT] [--round TEXT]

<run> is the data root of a running local `cad-http` and <out> the folder the screenshots go to.
The walk types the brief, confirms in the chat card and waits for the options. It clicks a face
of option 1, sends --thicker and waits for revision 2. Then it finds two edges by clicking along
the view until the chip names an edge, shift-clicks the second, sends --round and waits for
revision 3. It shoots each step in dark mode at 1440 px and exits 1 at the first step that did not
happen, naming it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import sync_playwright
from web_walk import ARGS, MISSED_SHOT, Missed, confirm, idle, options, page_for, say, shoot, step

if TYPE_CHECKING:
    from playwright.sync_api import Page

DEFAULTS = {
    "url": "http://127.0.0.1:8765",
    "account": "user_select",
    "brief": "An open box for my desk, 60 by 40 by 30 mm outside, with 2 mm walls.",
    "thicker": "Make this thicker.",
    "round": "Round these edges.",
}
GRID = 24
APART_PX = 60
REVISION = "() => /of {n}/.test(document.querySelector('[data-revisions]')?.innerText ?? '')"
CHIP = "[data-selection-chip]"


def chip(page: Page) -> str:
    found = page.locator(CHIP)
    return found.inner_text() if found.count() else ""


def click(page: Page, x: float, y: float, shift: bool = False) -> str:
    page.mouse.move(x, y)
    page.wait_for_timeout(80)
    if shift:
        page.keyboard.down("Shift")
    page.mouse.click(x, y)
    if shift:
        page.keyboard.up("Shift")
    page.wait_for_timeout(120)
    return chip(page)


def canvas_box(page: Page) -> tuple[float, float, float, float]:
    box = page.locator("[data-stage] canvas").first.bounding_box()
    if box is None:
        raise Missed("the stage has no canvas")
    return box["x"], box["y"], box["width"], box["height"]


def scan(page: Page, wanted: str) -> list[tuple[float, float]]:
    """Every grid point whose plain click selects exactly one `wanted` (face or edge)."""
    x0, y0, width, height = canvas_box(page)
    hits: list[tuple[float, float]] = []
    for row in range(1, GRID):
        for col in range(1, GRID):
            x, y = x0 + width * col / GRID, y0 + height * row / GRID
            if click(page, x, y).startswith(f"1 {wanted}"):
                hits.append((x, y))
    return hits


def picks(page: Page) -> int:
    found = page.locator("[data-picks]")
    return int(found.first.get_attribute("data-picks") or 0) if found.count() else 0


def two_edges(page: Page, points: list[tuple[float, float]]) -> None:
    """Shift-click hits until one adds a second edge. A hit on the first edge toggles it off."""
    if not points:
        raise Missed("no click selected an edge")
    click(page, *points[0])
    for point in points[1:]:
        if abs(point[0] - points[0][0]) + abs(point[1] - points[0][1]) <= APART_PX:
            continue
        click(page, *point, shift=True)
        if picks(page) == 2:
            return
        if picks(page) == 0:
            click(page, *points[0])
    raise Missed(f"no two different edges among {len(points)} edge hits")


def ask(page: Page, out: Path, text: str, revision: int, name: str) -> None:
    say(page, text)
    step("chip cleared", page, f"() => !document.querySelector('{CHIP}')", 30)
    step("said selection", page, "() => document.querySelector('[data-said-selection]')", 30)
    page.wait_for_timeout(3000)
    idle(page)
    if page.locator("[data-confirm-card] [data-confirm]").count():
        confirm(page)
    step(f"revision {revision}", page, REVISION.format(n=revision))
    idle(page)
    shoot(page, out, name)


def walk(run: Path, out: Path, given: dict[str, str]) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=ARGS)
        page = page_for(browser, run, given, 1440)
        page.goto(f"{given['url']}/app")
        step("chat start", page, "() => document.querySelector('textarea')", 30)
        say(page, given["brief"])
        step("project page", page, "() => location.pathname.includes('/projects/')")
        step("card", page, "() => document.querySelector('[data-confirm-card]')")
        idle(page)
        confirm(page)
        step("options", page, "() => document.querySelectorAll('[data-slot-tab]').length > 0")
        step("drawn", page, "() => document.querySelector('[data-stage] canvas')")
        idle(page)
        page.locator("[data-slot-tab='1']").click()
        page.wait_for_timeout(2000)
        x0, y0, width, height = canvas_box(page)
        if not click(page, x0 + width / 2, y0 + height / 2).startswith("1 face"):
            faces = scan(page, "face")
            if not faces:
                raise Missed("no click on option 1 selected a face")
            click(page, *faces[len(faces) // 2])
        step("face picked", page, "() => document.querySelector('[data-picks=\"1\"]')", 10)
        shoot(page, out, "select-1-face")
        ask(page, out, given["thicker"], 2, "select-2-thicker")
        page.wait_for_timeout(2000)
        two_edges(page, scan(page, "edge"))
        step("edges picked", page, "() => document.querySelector('[data-picks=\"2\"]')", 10)
        shoot(page, out, "select-3-edges")
        ask(page, out, given["round"], 3, "select-4-rounded")
        browser.close()


def main(argv: list[str]) -> int:
    rest, given = options(argv)
    given = {**DEFAULTS, **{key: given[key] for key in DEFAULTS if f"--{key}" in argv}}
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
