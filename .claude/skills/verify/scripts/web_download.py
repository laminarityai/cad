"""One live walk of the Download menu, then a check of each file it saved.

    uv run python .claude/skills/verify/scripts/browser.py web download <run> <out> [--url URL]
        [--account ID] [--project ID]

<run> is the data root of a running local `cad-http` (its `local-issuer.pem` signs the sign-in
token) and <out> the folder the screenshot and the files go to. The account must have a project
with a built option. The walk opens the newest project (or --project), opens the Download menu on
the option on screen and shoots it, then downloads STEP, STL and 3MF through the menu and saves
each under the name the server gave it. It then reads the scorecard of that revision and checks
the files against it: the STEP's SHA-256 is the card's `step` hash, the STL is a binary mesh whose
bounding box is the `extents` check's numbers, and the 3MF names millimetres and has the same
box. It prints one JSON line of numbers, and exits 1 at the first claim that does not hold. It
never prints or writes the sign-in token.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree

from playwright.sync_api import sync_playwright

from cad.accounts.local import LocalIssuer

if TYPE_CHECKING:
    from playwright.sync_api import Page

ARGS = ["--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"]
FORMATS = ("STEP", "STL", "3MF")
TOLERANCE_MM = 1e-3
DEFAULTS = {"url": "http://127.0.0.1:8765", "account": "user_web_proof", "project": ""}


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


def get_json(given: dict[str, str], token: str, path: str) -> Any:
    request = urllib.request.Request(given["url"] + path, headers={"Cookie": f"__session={token}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def on_screen(page: Page, given: dict[str, str], token: str, project: str) -> dict[str, str]:
    """The brief, the revision and the material the stage shows: slot 1's latest revision."""
    brief = get_json(given, token, f"/v1/projects/{project}")["briefs"][0]["brief_id"]
    seen = get_json(given, token, f"/v1/projects/{project}/briefs/{brief}/set")
    member = seen["members"][0]
    chosen: dict[str, str] | None = member["material"]
    material = "" if chosen is None else chosen["key"]
    return {"brief": brief, "variant": member["variant_id"], "material": material}


def stl_box(data: bytes) -> list[float]:
    (count,) = struct.unpack_from("<I", data, 80)
    if len(data) != 84 + 50 * count:
        raise Missed(f"the STL is not binary: {len(data)} bytes for {count} triangles")
    points = [
        struct.unpack_from("<3f", data, at + 12 + 12 * corner)
        for at in range(84, len(data), 50)
        for corner in range(3)
    ]
    return [max(p[a] for p in points) - min(p[a] for p in points) for a in range(3)]


def threemf_facts(data: bytes, path: Path) -> tuple[str | None, list[float]]:
    path.write_bytes(data)
    with zipfile.ZipFile(path) as archive:
        model = archive.read("3D/3dmodel.model").decode()
    unit = ElementTree.fromstring(model).get("unit")
    columns = [
        [float(v) for v in re.findall(rf'<vertex [^>]*\b{a}="([^"]+)"', model)] for a in "xyz"
    ]
    return unit, [max(c) - min(c) for c in columns]


def extents_of(card: dict[str, Any]) -> list[float]:
    result = next(one for one in card["results"] if one.get("check_id") == "extents")
    found = {m["name"]: m["value"] for m in result["measured"]}
    return [float(found[f"extent:{axis}"]["magnitude"]) for axis in "xyz"]


def download(page: Page, label: str, out: Path) -> Path:
    page.get_by_role("button", name="Download").click()
    with page.expect_download(timeout=180_000) as taken:
        page.get_by_role("menuitem", name=re.compile(f"^{label}")).click()
    saved = out / taken.value.suggested_filename
    taken.value.save_as(saved)
    page.get_by_role("button", name="Download").wait_for(timeout=10_000)
    return saved


def walk(run: Path, out: Path, given: dict[str, str]) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    token = LocalIssuer.open(run / "home", given["url"]).mint_person(given["account"])
    project = (
        given["project"] or get_json(given, token, "/v1/projects")["projects"][0]["project_id"]
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=ARGS)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
        context.add_cookies([{"name": "__session", "value": token, "url": given["url"]}])
        page = context.new_page()
        page.goto(f"{given['url']}/app/projects/{project}")
        page.wait_for_selector("[data-slot-tab]", timeout=30_000)
        page.wait_for_function(
            "() => { const v = [...document.querySelectorAll('[data-viewer]')];"
            " return v.length > 0 && v.every((one) => one.querySelector('canvas')); }",
            timeout=60_000,
        )
        shown = on_screen(page, given, token, project)
        page.get_by_role("button", name="Download").click()
        page.get_by_role("menuitem", name=re.compile("^STEP")).wait_for()
        page.screenshot(path=str(out / "download-menu.png"))
        page.keyboard.press("Escape")
        saved = {label: download(page, label, out) for label in FORMATS}
        browser.close()
    material = f"&material_key={shown['material']}" if shown["material"] else ""
    card = get_json(
        given,
        token,
        f"/v1/variants/{shown['variant']}/scorecard?brief_id={shown['brief']}{material}",
    )
    return facts(card, saved, out, shown)


def facts(
    card: dict[str, Any], saved: dict[str, Path], out: Path, shown: dict[str, str]
) -> dict[str, Any]:
    measured = extents_of(card)
    step_sha = hashlib.sha256(saved["STEP"].read_bytes()).hexdigest()
    stl = stl_box(saved["STL"].read_bytes())
    unit, threemf = threemf_facts(saved["3MF"].read_bytes(), out / "check.3mf")
    (out / "check.3mf").unlink()
    report = {
        "variant": shown["variant"],
        "files": {label: [path.name, path.stat().st_size] for label, path in saved.items()},
        "extents_check_mm": measured,
        "stl_box_mm": stl,
        "threemf_box_mm": threemf,
        "threemf_unit": unit,
        "step_sha256": step_sha,
        "card_step_sha256": card["step"].get("sha256"),
    }
    if step_sha != report["card_step_sha256"]:
        raise Missed(f"the STEP is not the card's STEP: {json.dumps(report)}")
    for name, box in (("STL", stl), ("3MF", threemf)):
        if any(abs(a - b) > TOLERANCE_MM for a, b in zip(box, measured, strict=True)):
            raise Missed(f"the {name} box is not the extents check's: {json.dumps(report)}")
    if unit != "millimeter":
        raise Missed(f"the 3MF unit is {unit!r}: {json.dumps(report)}")
    return report


def main(argv: list[str]) -> int:
    rest, given = options(argv)
    if len(rest) != 2:
        print(__doc__)
        return 2
    try:
        report = walk(Path(rest[0]), Path(rest[1]), given)
    except Missed as error:
        print(f"MISSED: {error}")
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
