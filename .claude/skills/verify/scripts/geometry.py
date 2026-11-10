"""Usage: uv run python .claude/skills/verify/scripts/geometry.py <evidence_dir> <part.py>...

Builds and scores each part through the cad MCP server on stdio, with HOME set to
<evidence_dir>/home, then reads its mesh through the registry's person-only `geometry`
operation, the way the web app's route will. It prints the mass check's volume beside the mesh
volume and fails when they differ by more than 0.5%. For each part it writes <name>.json (the
three-cad-viewer shapes), <name>.html (a page that renders them with three-cad-viewer from a
CDN) and <name>.png (a headless Chromium screenshot of that page).
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import anyio
from mcp import Client, StdioServerParameters
from playwright.sync_api import sync_playwright

from cad.accounts.tenants import open_tenant
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.geometry.model import Tessellated, TessellationPending, mesh_volume
from cad.operations.model import Audience, Tenant
from cad.operations.registry import OPERATIONS
from cad.records.roots import Roots
from cad.server.app import LOCAL

AGREEMENT = 0.005
VIEWER = "https://cdn.jsdelivr.net/npm/three-cad-viewer@5.1.3/dist"
PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{name}</title>
<link rel="stylesheet" href="{viewer}/three-cad-viewer.css">
<style>body {{ margin: 0; background: #fff; }}</style>
<script type="module">
import {{ Viewer, Display }} from "{viewer}/three-cad-viewer.esm.js";
const shapes = {shapes};
const display = new Display(document.getElementById("cad"), {{
  cadWidth: 900, height: 600, treeWidth: 240, theme: "light", glass: false, tools: true,
}});
const viewer = new Viewer(display, {{ target: [0, 0, 0], up: "Z" }}, () => {{}});
viewer.render(shapes, {{ edgeColor: 0x707070, defaultOpacity: 0.5, normalLen: 0 }},
  {{ target: [0, 0, 0], up: "Z" }});
window.rendered = true;
</script></head>
<body><div id="cad"></div></body></html>
"""


def server(home: Path) -> StdioServerParameters:
    env = {name: os.environ[name] for name in ("PATH", "USER", "LOGNAME") if name in os.environ}
    return StdioServerParameters(
        command=sys.executable, args=["-m", "cad.server"], env={**env, "HOME": str(home)}
    )


async def score(home: Path, code: str) -> tuple[str, float]:
    async with Client(server(home)) as client:
        built = await client.call_tool("build_variant", {"code": code})
        assert not built.is_error and built.structured_content, built.content
        variant_id = built.structured_content["variant_id"]
        arguments = {"variant_id": variant_id, "material_key": "prusament-pla"}
        scored = await client.call_tool("score_variant", arguments)
        assert not scored.is_error and scored.structured_content, scored.content
    results: list[dict[str, Any]] = scored.structured_content["results"]
    mass = next(one for one in results if one["check_id"] == "mass")
    volume = next(one["value"] for one in mass["measured"] if one["name"] == "volume")
    assert volume["unit"] == "mm³", volume
    return variant_id, float(volume["magnitude"])


def tenant(home: Path) -> Tenant:
    cad = home / ".cad"
    roots = Roots(cad / "briefs", cad / "projects")
    return open_tenant(LOCAL, roots, cad / "variants", cad / "geometry", None, Door(), ingest)


def read_geometry(home: Path, variant_id: str) -> Tessellated:
    geometry = next(one for one in OPERATIONS if one.name == "geometry")
    assert geometry.audience == Audience.PERSON, geometry.audience
    arguments = geometry.input.model_validate({"variant_id": variant_id})
    deadline = time.monotonic() + 120
    while True:
        read = geometry.run(tenant(home), arguments)
        if not isinstance(read, TessellationPending):
            assert isinstance(read, Tessellated), read
            return read
        assert time.monotonic() < deadline, "the tessellation never finished"
        time.sleep(0.5)


def screenshot(page_path: Path, png: Path) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1180, "height": 660})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(page_path.as_uri())
        page.wait_for_function("window.rendered === true", timeout=60_000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(png))
        browser.close()
    assert not errors, errors


def main(evidence: Path, parts: list[Path]) -> int:
    home = evidence / "home"
    home.mkdir(parents=True, exist_ok=True)
    worst = 0.0
    for part in parts:
        variant_id, volume = anyio.run(score, home, part.read_text())
        read = read_geometry(home, variant_id)
        meshed = mesh_volume(read.shapes["parts"][0]["shape"])
        off = abs(meshed - volume) / volume
        worst = max(worst, off)
        print(
            f"{part.stem}: variant {variant_id}, brep {read.brep_sha256[:12]}, mass check volume "
            f"{volume:.3f} mm^3, mesh volume {meshed:.3f} mm^3, off by {off:.4%}"
        )
        shapes = json.dumps(read.shapes)
        (evidence / f"{part.stem}.json").write_text(shapes)
        page = evidence / f"{part.stem}.html"
        page.write_text(PAGE.format(name=part.stem, viewer=VIEWER, shapes=shapes))
        screenshot(page, evidence / f"{part.stem}.png")
    print(f"worst agreement {worst:.4%}, limit {AGREEMENT:.1%}")
    return 0 if worst <= AGREEMENT else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), [Path(arg) for arg in sys.argv[2:]]))
