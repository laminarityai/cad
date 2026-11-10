"""A signed-in person in a real browser on the web app, for `browser.py web ...`.

    uv run python .claude/skills/verify/scripts/browser.py web shot <run> <path> <name> [options]
    uv run python .claude/skills/verify/scripts/browser.py web watch <run> <path> <name> [options]
    uv run python .claude/skills/verify/scripts/browser.py web chat <run> <path> <name> [options]

<run> is the data root of a local `cad-http` (its `local-issuer.pem` signs the sign-in token),
<path> is a route of the app such as `/projects/<id>/briefs/<id>`, and <name> is the prefix of the
files written into <run>. Options: --url (the server, default http://127.0.0.1:8765), --account
(default user_web_proof), --width, --height, --scheme (light or dark), --seconds (watch, default
120), --material (a material key to pick in the page's select before it starts), --tab (a
narrow-screen tab to show: Chat, Model or Scorecard).

`shot` opens the page, waits until every viewer has drawn, and writes <name>.png and
<name>.aria.yml (the page's accessibility tree). `watch` opens the page and polls its rows while
something else scores the variants. It writes <name>-pending.png when it first sees a pending row,
<name>-done.png once none is left, and <name>.sse.jsonl (every scorecard event the page received,
and when) and <name>.rows.jsonl (every change of a row). It exits 1 when a pending row ever wears a
verdict, or when no row went from pending to a verdict without a navigation.

`chat` drives the chat panel against a server whose model is a script (`CAD_CHAT_MODEL`), and
records a video of it in <name>.webm. It picks Plan and asks for a change (the server refuses
the build), picks Design and asks again, and times how long slot 1 takes to show revision 2, to
go all pending and to wear verdicts again, with no navigation. Then it picks Auto, sends a
message, waits for the run status, presses Stop, and checks that the picker reads Design and a
stopped report shows. It writes <name>-plan.png, -before.png, -after.png, -auto.png,
-stopped.png, <name>.aria.yml and <name>.chat.json (the timings), and exits 1 when a step did
not happen. Options for `chat` only: --ask (the message to type for the change, default "make
the wall 4 mm"), --auto_ask (the message that starts Auto), --video (a directory, to record
into, default off), and --live true for a real model: it waits for each turn to end instead of
for the script's words, and does not require the Plan refusal. --stop switch leaves Auto with
the mode picker instead of the Stop button, which stops the run the same way.
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
TAP = """
window.__sse = [];
const Real = window.EventSource;
window.EventSource = class extends Real {
  constructor(url, init) {
    super(url, init);
    this.addEventListener("scorecard", (event) => {
      const etag = JSON.parse(event.data).etag;
      window.__sse.push({ at: Date.now(), url, bytes: event.data.length, etag });
    });
  }
};
"""
ROWS = """
() => [...document.querySelectorAll("[data-row]")].map((row) => ({
  key: row.dataset.key, kind: row.dataset.row,
  tones: [...row.querySelectorAll("[data-tone]")].map((one) => one.dataset.tone),
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
        "material": "",
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
    context.add_init_script(TAP)
    page = context.new_page()
    page.goto(f"{given['url']}/app{path}")
    page.evaluate("window.__alive = true")
    return browser, page


def drawn(page: Page) -> None:
    page.wait_for_selector("[data-slot-tile]", timeout=30_000)
    page.wait_for_function(
        "() => { const v = [...document.querySelectorAll('[data-viewer]')];"
        " const t = document.querySelectorAll('[data-slot-tile]').length;"
        " return v.length === t && v.every((one) => one.querySelector('canvas')); }",
        timeout=60_000,
    )
    page.wait_for_timeout(500)


def open_tab(page: Page, name: str) -> None:
    tab = page.get_by_role("tab", name=name)
    if tab.count():
        tab.click()
        page.wait_for_timeout(300)


def pick_material(page: Page, given: dict[str, str]) -> None:
    if given["material"]:
        if not page.locator("select").first.is_visible():
            open_tab(page, "Scorecard")
        page.select_option("select", given["material"])
        page.wait_for_timeout(500)
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
    was_pending: set[str] = set()
    wearing: list[str] = []
    replaced: list[str] = []
    with sync_playwright() as playwright:
        browser, page = open_page(playwright, run, path, given)
        drawn(page)
        pick_material(page, given)
        navigations: list[str] = []
        page.on("framenavigated", lambda frame: navigations.append(frame.url))
        last: dict[str, tuple[str, tuple[str, ...]]] = {}
        shots: set[str] = set()
        with (run / f"{name}.rows.jsonl").open("w") as log:
            while time.time() - started < float(given["seconds"]):
                rows = page.evaluate(ROWS)
                for row in rows:
                    state = (row["kind"], tuple(row["tones"]))
                    if last.get(row["key"]) != state:
                        log.write(json.dumps({"at": time.time(), **row}) + "\n")
                        log.flush()
                    if row["kind"] == "pending":
                        was_pending.add(row["key"])
                        if VERDICTS & set(row["tones"]):
                            wearing.append(row["key"])
                    elif row["key"] in was_pending and last.get(row["key"], ("",))[0] == "pending":
                        replaced.append(row["key"])
                    last[row["key"]] = state
                if rows and any(r["kind"] == "pending" for r in rows) and "pending" not in shots:
                    shots.add("pending")
                    page.screenshot(path=str(run / f"{name}-pending.png"))
                if shots and rows and all(r["kind"] != "pending" for r in rows):
                    page.wait_for_timeout(400)
                    page.screenshot(path=str(run / f"{name}-done.png"))
                    break
                page.wait_for_timeout(250)
        events = page.evaluate("window.__sse")
        (run / f"{name}.sse.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        (run / f"{name}.aria.yml").write_text(page.locator("body").aria_snapshot())
        browser.close()
    print(
        json.dumps(
            {
                "pending_rows_seen": sorted(was_pending),
                "replaced_in_place": sorted(set(replaced)),
                "pending_rows_wearing_a_verdict": wearing,
                "navigations_after_load": navigations,
                "events": len(events),
            }
        )
    )
    return 0 if replaced and not wearing and not navigations else 1


SLOT_LOG = """
() => {
  window.__slotLog = [];
  const read = () => {
    const t = document.querySelector("[data-slot-tile='1']");
    const m = t && /revision (\\d+)/.exec(t.textContent || "");
    const host = t && t.querySelector("[data-draws]");
    return { rev: m ? Number(m[1]) : 0, draws: host ? Number(host.dataset.draws) : 0 };
  };
  let last = "";
  setInterval(() => {
    const now = read();
    const key = JSON.stringify(now);
    if (key !== last) { last = key; window.__slotLog.push({ at: performance.now(), ...now }); }
  }, 16);
}
"""


def swap_seconds(page: Page, revision_before: int) -> float:
    log: list[dict[str, float]] = page.evaluate("window.__slotLog")
    old = [one for one in log if one["rev"] == revision_before]
    new = [one for one in log if one["rev"] > revision_before]
    if not old or not new:
        return 0.0
    drawn = next((one for one in new if one["draws"] > old[-1]["draws"]), None)
    if drawn is None:
        return 0.0
    return round((drawn["at"] - swap_start(old, new, drawn)["at"]) / 1000, 3)


def swap_start(
    old: list[dict[str, float]], new: list[dict[str, float]], drawn: dict[str, float]
) -> dict[str, float]:
    one_blocked_tick_saw_both = drawn is new[0]
    return old[-1] if one_blocked_tick_saw_both else new[0]


def tiles(page: Page) -> dict[str, Any]:
    return page.evaluate(
        "() => { const t = document.querySelector('[data-slot-tile=\"1\"]');"
        " if (!t) return {revision: 0, tones: []};"
        " const m = /revision (\\d+)/.exec(t.textContent || '');"
        " return {revision: m ? Number(m[1]) : 0,"
        " tones: [...t.querySelectorAll('[data-tone]')].map((i) => i.dataset.tone)}; }"
    )


def mode_of(page: Page) -> str:
    return page.locator("[data-mode]").first.get_attribute("data-mode") or ""


def pick_mode(page: Page, label: str) -> None:
    page.locator("[data-mode]").first.click()
    page.get_by_role("menuitemradio", name=label).click()
    page.wait_for_timeout(600)


def say(page: Page, text: str) -> None:
    box = page.get_by_label("Message to the agent")
    box.fill(text)
    box.press("Enter")


def run_status(page: Page) -> str:
    return page.locator("[data-run]").first.get_attribute("data-run") or "none"


def wait_for(page: Page, probe: str, seconds: float) -> bool:
    try:
        page.wait_for_function(probe, timeout=seconds * 1000, polling=100)
    except Exception:
        return False
    return True


def turn_finished(page: Page, seconds: float) -> bool:
    working = "() => document.body.innerText.includes('Working…')"
    wait_for(page, working, 30)
    page.wait_for_timeout(500)
    return wait_for(page, f"() => !({working[6:]})", seconds)


SHOWN = """visibility => {
  Object.defineProperty(document, "visibilityState", { value: visibility, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
}"""


def stop_in_another_tab(page: Page, run: Path, name: str) -> dict[str, Any]:
    """Stop the run from a second tab of the same browser, as a person switching tabs does.
    Playwright keeps every page visible, so each switch sets `visibilityState` and fires
    `visibilitychange`, as the browser does on a real tab switch."""
    page.evaluate(SHOWN, "hidden")
    other = page.context.new_page()
    other.goto(page.url)
    open_tab(other, "Chat")
    button = other.get_by_role("button", name="Stop")
    button.first.wait_for(timeout=30_000)
    button.first.click()
    stopped = wait_for(other, "() => document.querySelector('[data-run=stopped]') !== null", 30)
    other.screenshot(path=str(run / f"{name}-other-tab.png"))
    other.evaluate(SHOWN, "hidden")
    page.bring_to_front()
    page.evaluate(SHOWN, "visible")
    return {"other_tab_stopped": stopped}


def chat(run: Path, path: str, name: str, given: dict[str, str]) -> int:
    live = given["live"] == "true"
    found: dict[str, Any] = {"live": live}
    meshes: list[float] = []
    with sync_playwright() as playwright:
        browser, page = open_page(playwright, run, path, given)
        drawn(page)
        pick_material(page, given)
        page.on(
            "response",
            lambda r: meshes.append(time.time()) if "/v1/geometry/" in r.url and r.ok else None,
        )
        open_tab(page, "Model")
        page.locator("[data-slot-tile='1'] button").first.click()
        open_tab(page, "Chat")
        pick_mode(page, "Plan")
        found["plan_picked"] = mode_of(page) == "plan"
        say(page, given["ask"])
        if live:
            found["plan_refused"] = turn_finished(page, 180)
        else:
            found["plan_refused"] = wait_for(
                page, "() => document.body.innerText.includes('Plan mode')", 60
            ) and wait_for(page, "() => /Switch to Design/.test(document.body.innerText)", 60)
        page.screenshot(path=str(run / f"{name}-plan.png"))
        open_tab(page, "Model")
        before = tiles(page)
        found["revision_before"] = before["revision"]
        found["slot_untouched_in_plan"] = before["tones"] != [] and "pending" not in before["tones"]
        page.screenshot(path=str(run / f"{name}-before.png"))
        open_tab(page, "Chat")
        pick_mode(page, "Design")
        found["design_picked"] = mode_of(page) == "design"
        page.evaluate(SLOT_LOG)
        started = time.time()
        say(page, given["ask"])
        open_tab(page, "Model")
        trail: list[tuple[float, int, tuple[str, ...]]] = []
        shot_pending = False
        t_revision = t_pending = t_verdict = t_mesh = 0.0
        while time.time() - started < 240 and not (t_verdict and t_mesh):
            now = tiles(page)
            at = time.time() - started
            tones = tuple(now["tones"])
            if not trail or trail[-1][1:] != (now["revision"], tones):
                trail.append((round(at, 2), now["revision"], tones))
            if now["revision"] > before["revision"] and not t_revision:
                t_revision = at
            if t_revision and tones and set(tones) == {"pending"} and not t_pending:
                t_pending = at
            if t_pending and tones and "pending" not in tones:
                t_verdict = at
            ready = "[data-slot-tile='1'] [data-mesh=ready] canvas"
            if t_revision and not t_mesh and page.locator(ready).count():
                t_mesh = at
            if t_pending and not shot_pending:
                shot_pending = True
                page.screenshot(path=str(run / f"{name}-pending.png"))
            page.wait_for_timeout(50)
        swap = swap_seconds(page, before["revision"])
        found.update(
            seconds_pending_to_mesh=swap,
            seconds_to_revision=round(t_revision, 2),
            seconds_to_pending=round(t_pending, 2),
            seconds_to_verdicts=round(t_verdict, 2),
            seconds_to_mesh=round(t_mesh, 2),
            mesh_requests_after_rebuild=sum(1 for at in meshes if at >= started + t_revision),
            slot_trail=trail,
        )
        page.screenshot(path=str(run / f"{name}-after.png"))
        open_tab(page, "Chat")
        if live:
            found["agent_replied"] = turn_finished(page, 240)
        else:
            found["agent_replied"] = wait_for(
                page, "() => /Slot 1 now has a 4 mm wall/.test(document.body.innerText)", 90
            )
        open_tab(page, "Chat")
        pick_mode(page, "Auto")
        found["auto_picked"] = mode_of(page) == "auto"
        say(page, given["auto_ask"])
        found["run_started"] = wait_for(
            page, "() => document.querySelector('[data-run=running]') !== null", 90
        )
        page.wait_for_timeout(500)
        page.screenshot(path=str(run / f"{name}-auto.png"))
        found["revisions_while_running"] = page.locator("[data-run]").first.inner_text()
        stop = page.get_by_role("button", name="Stop")
        found["stop_visible"] = stop.count() > 0
        pressed = time.time()
        if given["stop"] == "switch":
            pick_mode(page, "Design")
            page.screenshot(path=str(run / f"{name}-switch.png"))
        elif given["stop"] == "elsewhere":
            found.update(stop_in_another_tab(page, run, name))
            pressed = time.time()
        elif stop.count():
            stop.first.click()
        found["moved_to_design"] = wait_for(
            page, "() => document.querySelector('[data-mode=design]') !== null", 30
        )
        found["stopped_report"] = wait_for(
            page, "() => document.querySelector('[data-run=stopped]') !== null", 90
        )
        found["seconds_stop_to_shown"] = round(time.time() - pressed, 2)
        page.wait_for_timeout(500)
        report = page.locator("[data-run] summary")
        if report.count():
            report.first.click()
        page.screenshot(path=str(run / f"{name}-stopped.png"))
        found["status_after_stop"] = page.locator("[data-run]").first.inner_text()
        found["no_reload"] = bool(page.evaluate("window.__alive === true"))
        (run / f"{name}.aria.yml").write_text(page.locator("body").aria_snapshot())
        video = page.video
        page.close()
        if video is not None and given["video"]:
            video.save_as(str(run / f"{name}.webm"))
        browser.close()
    (run / f"{name}.chat.json").write_text(json.dumps(found, indent=1))
    print(json.dumps(found))
    needed = [
        "plan_picked", "plan_refused", "slot_untouched_in_plan", "design_picked", "no_reload",
        "agent_replied", "auto_picked", "run_started", "stop_visible", "moved_to_design",
        "stopped_report",
    ]  # fmt: skip
    if given["stop"] == "elsewhere":
        needed.append("other_tab_stopped")
    ok = all(found.get(key) for key in needed) and bool(found["seconds_to_verdicts"])
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    rest, given = options(argv)
    match rest:
        case ["shot", run, path, name]:
            return shot(Path(run), path, name, given)
        case ["watch", run, path, name]:
            return watch(Path(run), path, name, given)
        case ["chat", run, path, name]:
            return chat(Path(run), path, name, given)
        case _:
            print(__doc__)
            return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
