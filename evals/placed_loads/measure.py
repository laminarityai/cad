"""Build step 1 of docs/design/fea-agent-placed-loads.md: what code placement decides, and whether
the design's assumptions hold, measured in the build and analysis images.

    uv run python evals/placed_loads/measure.py faces <out.jsonl> [part ...]
    uv run python evals/placed_loads/measure.py solve <out.jsonl> <placement label> ...
    uv run python evals/placed_loads/measure.py table <faces.jsonl> <solve.jsonl>

`faces` builds each part, reads its explorer order in both images, turns and moves it, resolves
its reviewed and described cases, and runs its placements without solving. `solve` runs a
placement through today's `fea` check. `table` prints the tables the design note quotes."""

import json
import sys
import time
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Final, cast

from corpus import BY_NAME, CORPUS, FORCE_N, NOVICE, Part
from placements import PLACEMENTS, SIDE, Placement
from table import tables

from cad.agent_checks import turned
from cad.agent_checks.harness import Motion
from cad.checks.report import IMAGE_TAG
from cad.sandbox import builder, container, image
from cad.sandbox.container import Job, ReadOnlyMount
from cad.sandbox.stage import TARGET, check_mount, read_sources

INSIDE: Final = Path(__file__).resolve().parent / "inside"
PROBE: Final = "/opt/probe"
BOOT: Final = f"import sys; sys.path[:0] = [{TARGET!r}, {PROBE!r}]; from probe import main; main()"
SOURCES: Final = read_sources("cad.checks.container.fea", "cad.checks.container.runner")
VALUES: Final = {
    "elastic_modulus": {"kind": "known", "magnitude": 2300.0},
    "poisson_ratio": {"kind": "known", "magnitude": 0.34},
    "yield_strength": {"kind": "known", "magnitude": 51.0},
}
BUILD_SECONDS: Final = 120
FACES_SECONDS: Final = 300
SOLVE_SECONDS: Final = 1800
"""Above the check's 600 s budget, so a solve that would time out in the product still reports
how long it takes."""
SOLVE_MEMORY_MB: Final = 2048
SOLVE_TMPFS_MB: Final = 768
"""The `fea` check's own budget (`fea.BUDGET`)."""


def built(code: str) -> bytes:
    ran = builder.build(code, image.current_image(image.image_tag(image.BUILD)), wall_seconds=120)
    if not isinstance(ran.verdict, builder.Artifacts):
        raise RuntimeError(f"the part did not build: {ran.verdict}")
    return ran.verdict.brep


def side(brep: bytes, codes: Mapping[str, str]) -> dict[str, object]:
    """The build image's explorer order and each placement's candidates."""
    tag = image.image_tag(image.BUILD)
    job = Job(
        "build",
        image.current_image(tag),
        ("python", "-I", "-c", SIDE, json.dumps(dict(codes))),
        brep,
        wall_seconds=BUILD_SECONDS,
    )
    return cast(dict[str, object], _report(container.run(job), "build side"))


def analysis(brep: bytes, job: Mapping[str, object], wall_seconds: int) -> object:
    ran = container.run(
        Job(
            "check",
            image.current_image(IMAGE_TAG),
            ("python", "-I", "-c", BOOT, json.dumps(job)),
            brep,
            (check_mount(SOURCES), ReadOnlyMount(INSIDE, PROBE)),
            wall_seconds=wall_seconds,
            memory_mb=SOLVE_MEMORY_MB,
            tmpfs_mb=SOLVE_TMPFS_MB,
        )
    )
    return _report(ran, "analysis")


def _report(ran: container.Ran, where: str) -> object:
    report = ran.attended.report
    if ran.state.ExitCode != 0 or not isinstance(report, bytes) or not report:
        raise RuntimeError(
            f"the {where} run exited {ran.state.ExitCode}, oom {ran.state.OOMKilled}, killed "
            f"{ran.attended.killed_at_deadline}: {ran.attended.output[-1500:]}"
        )
    return json.loads(report)


def placements_of(part: Part) -> tuple[Placement, ...]:
    return tuple(one for one in PLACEMENTS if one.part == part.name)


def faces_row(part: Part) -> dict[str, object]:
    start = time.monotonic()
    brep = built(part.code)
    codes = {one.label: one.code for one in placements_of(part)}
    cases = [{"label": label, "wire": wire} for label, wire in part.described]
    if part.reviewed is not None:
        cases.insert(0, {"label": "reviewed", "wire": part.reviewed})
    row: dict[str, object] = {
        "part": part.name,
        "words": part.words,
        "corpus": part.reviewed is not None,
        "side": side(brep, codes),
        "kernel": analysis(brep, {"mode": "faces", "cases": cases}, FACES_SECONDS),
    }
    motion = Motion.drawn()
    moved = turned.turn(brep, motion)
    row["motion"] = asdict(motion)
    if isinstance(moved, str):
        row["turn_failed"] = moved
    else:
        row["turned_kernel"] = analysis(moved, {"mode": "faces", "cases": []}, FACES_SECONDS)
        row["turned_side"] = side(moved, codes)
    if codes:
        side_row = cast(dict[str, object], row["side"])
        found = cast(dict[str, dict[str, object]], side_row["placements"])
        jobs = [
            {"label": label, "candidates": found[label].get("candidates", []), "solve": False}
            for label in codes
        ]
        row["placed"] = analysis(brep, {"mode": "placed", "placements": jobs}, FACES_SECONDS)
    row["seconds"] = time.monotonic() - start
    return row


def solve_row(placement: Placement) -> dict[str, object]:
    brep = built(BY_NAME[placement.part].code)
    found = cast(dict[str, dict[str, object]], side(brep, {placement.label: placement.code}))
    picked = cast(dict[str, dict[str, object]], found["placements"])[placement.label]
    job = {
        "mode": "placed",
        "placements": [
            {"label": placement.label, "candidates": picked["candidates"], "solve": True}
        ],
        "values": VALUES,
        "force_n": FORCE_N,
    }
    start = time.monotonic()
    (result,) = cast(list[dict[str, object]], analysis(brep, job, SOLVE_SECONDS))
    return {
        "label": placement.label,
        "part": placement.part,
        "words": placement.words,
        "placement_seconds": picked["seconds"],
        "container_seconds": time.monotonic() - start,
        **result,
    }


def append(out: Path, row: Mapping[str, object]) -> None:
    with out.open("a") as stream:
        stream.write(json.dumps(row) + "\n")
    print(json.dumps(row)[:400], flush=True)


def main(argv: list[str]) -> None:
    command, *rest = argv
    if command == "table":
        rows = [
            [json.loads(line) for line in Path(path).read_text().splitlines() if line]
            for path in rest
        ]
        print(tables(rows[0], rows[1] if len(rows) > 1 else []))
        return
    out, *names = rest
    if command == "faces":
        chosen = [BY_NAME[name] for name in names] or [*CORPUS, *NOVICE]
        for part in chosen:
            append(Path(out), faces_row(part))
    elif command == "solve":
        labelled = {one.label: one for one in PLACEMENTS}
        for label in names or list(labelled):
            append(Path(out), solve_row(labelled[label]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
