"""Usage: uv run python .claude/skills/verify/scripts/chat_seed.py <run> <account> <port> [label]

Seeds a local `cad-http` (data root <run>/home, port <port>) for `browser.py web chat`: a brief
with confirmed requirements, three scored variants in slots 1 to 3, and a script for
`CAD_CHAT_MODEL` at <run>/seed/script/script.json. The server must run with the browser daemon's
`bin/open` as its opener, so that the confirmation page is answered. It prints the project and
brief ids as JSON. `label` is added to the brief's words and each part's code, so a second seed
is a new brief with new variants. Without it, code that is already built is the same variant,
and its checks do not run again.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

MATERIAL = "polymaker-polylite-abs"
WORDS = (
    "A PolyLite ABS cantilever channel, 100 x 20 x 10 mm, under 150 g, "
    "that bends at most 2 mm under 10 N at its free end."
)
WALLS = {"wall1": 1, "wall2": 2, "wall3": 3, "wall4": 4, "wall5": 5, "wall6": 6, "wall35": 3.5}
CASE = {
    "support": {"kind": "flat_end"},
    "load": {
        "kind": "far_end",
        "force": {"magnitude": 10, "unit": "N"},
        "direction": {"kind": "across", "axis": "long"},
    },
}


def main(argv: list[str]) -> int:
    run, account, port = argv[0], argv[1], argv[2]
    label = argv[3] if len(argv) > 3 else ""
    url = f"http://127.0.0.1:{port}"
    scripts = Path(run) / "seed" / "script"
    scripts.mkdir(parents=True, exist_ok=True)
    token = subprocess.check_output(
        ["uv", "run", "cad-token", "--root", f"{run}/home", "--url", url, "agent", account],
        text=True,
    ).strip()

    def call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        command = ["uv", "run", "cad-call", "--url", f"{url}/mcp", "--token", token]
        out = subprocess.check_output([*command, tool, json.dumps(arguments)], text=True)
        return json.loads(out)["structuredContent"]

    for name, wall in WALLS.items():
        (scripts / f"{name}.py").write_text(
            "from build123d import Box\n\n"
            f"# a channel, 100 mm long, with a {wall} mm side wall{label}\n"
            f"result = Box(100, 20, 10) - Box(100, 20 - 2 * {wall}, 6)\n"
        )
    brief = call("create_brief", {"text": WORDS + label})
    bid, pid = brief["brief_id"], brief["project_id"]
    call(
        "propose_requirements",
        {
            "brief_id": bid,
            "requirements": [
                {"target": {"kind": "made_of", "material": MATERIAL}, "quote": "PolyLite ABS"},
                {
                    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
                    "quote": "under 150 g",
                },
                {
                    "target": {
                        "kind": "max_deflection",
                        "load": CASE,
                        "deflection": {"magnitude": 2, "unit": "mm"},
                    },
                    "quote": "bends at most 2 mm under 10 N at its free end",
                },
            ],
        },
    )
    answered = call("ask_to_confirm", {"project_id": pid})
    assert answered["status"] == "answered", answered
    ids = [
        call("build_variant", {"code": (scripts / f"{w}.py").read_text(), "brief_id": bid})[
            "variant_id"
        ]
        for w in ("wall3", "wall2", "wall1")
    ]
    for variant in ids:
        for _ in range(60):
            scored = call(
                "score_variant",
                {"variant_id": variant, "material_key": MATERIAL, "brief_id": bid},
            )
            if not scored.get("pending"):
                break
            time.sleep(3)

    def step(text: str, name: str, **arguments: Any) -> dict[str, Any]:
        return {"text": text, "calls": [{"name": name, "input": arguments}]}

    def revise(file: str) -> dict[str, Any]:
        return step(
            f"Revising: {file}",
            "auto_revise",
            run_id="${auto_start.run_id}",
            code=f"@file:{file}",
            slot=2,
        )

    steps = [
        step(
            "I will thicken the wall.", "build_variant", code="@file:wall4.py", brief_id=bid, slot=1
        ),
        {"text": "Plan mode does not build. Switch to Design and ask again."},
        step(
            "Rebuilding slot 1 with a 4 mm wall.",
            "build_variant",
            code="@file:wall4.py",
            brief_id=bid,
            slot=1,
        ),
        step(
            "Scoring it.",
            "score_variant",
            variant_id="${build_variant.variant_id}",
            material_key=MATERIAL,
            brief_id=bid,
        ),
        {"text": "Slot 1 now has a 4 mm wall. The scorecard shows what the checks measured."},
        step("Starting the run.", "auto_start", brief_id=bid, material_key=MATERIAL),
        *(revise(f"{w}.py") for w in ("wall5", "wall6", "wall35", "wall5")),
        {"text": "The run is going."},
    ]
    (scripts / "script.json").write_text(json.dumps({"steps": steps}, indent=1))
    print(json.dumps({"project": pid, "brief": bid, "variants": ids}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
