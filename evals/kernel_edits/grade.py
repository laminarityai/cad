"""Grade a variant's STEP file against one edit or assembly brief.

Every check runs and reports, so a result says both whether the requested change is
there and whether the edit broke anything else. `category` names the first failing
check in CHECKS order, or `pass`.

The grader reads three fingerprints: the brief's starting model, its reference and the
variant. Surfaces the reference shares with the starting model are untouched features.
Surfaces only the reference has are the target of the change. Surfaces only the starting
model has must be gone.
"""

import bisect
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

import yaml

from fingerprint import Model, Solid, Surface, common_volume, load

ROOT = Path(__file__).resolve().parent
PARAM_TOL = 1e-3
AREA_REL_TOL = 1e-4
AREA_ABS_TOL = 1e-3
VOLUME_REL_TOL = 1e-4
VOLUME_ABS_TOL = 1e-2
BBOX_TOL = 1e-2
INTERFERENCE_TOL = 1e-2
SHOWN = 3

CheckName = Literal["solids", "interference", "target", "untouched", "shape"]
Category = Literal[
    "pass", "no_output", "invalid_solid", "interference", "target", "untouched", "shape"
]
CHECKS: tuple[tuple[CheckName, Category], ...] = (
    ("solids", "invalid_solid"),
    ("interference", "interference"),
    ("target", "target"),
    ("untouched", "untouched"),
    ("shape", "shape"),
)


@dataclass(frozen=True, slots=True)
class Brief:
    id: str
    kind: Literal["edit", "assembly"]
    start: str
    text: str


@dataclass(frozen=True, slots=True)
class Check:
    passed: bool
    detail: str


@cache
def briefs() -> dict[str, Brief]:
    raw: list[dict[str, str]] = yaml.safe_load((ROOT / "briefs.yaml").read_text())
    parsed = [Brief(b["id"], parse_kind(b["kind"]), b["start"], b["brief"]) for b in raw]
    return {b.id: b for b in parsed}


def parse_kind(kind: str) -> Literal["edit", "assembly"]:
    if kind == "edit" or kind == "assembly":
        return kind
    raise ValueError(f"brief kind must be edit or assembly, not {kind!r}")


def reference_path(brief_id: str) -> Path:
    return ROOT / "reference" / f"{brief_id}.step"


def start_path(start_id: str) -> Path:
    return ROOT / "reference" / "start" / f"{start_id}.step"


@cache
def stored(path: Path) -> Model:
    model = load(path)
    if model is None:
        raise FileNotFoundError(f"{path} is missing or unreadable; run reference/build.py")
    return model


def grade(brief_id: str, step_path: Path) -> dict[str, object]:
    brief = briefs()[brief_id]
    start = stored(start_path(brief.start))
    reference = stored(reference_path(brief_id))
    return {"brief": brief_id, **grade_models(start, reference, load(step_path))}


def grade_models(start: Model, reference: Model, variant: Model | None) -> dict[str, object]:
    if variant is None:
        return {"pass": False, "category": "no_output", "checks": {}, "measured": {}}
    checks = run_checks(start, reference, variant)
    failed = [category for name, category in CHECKS if not checks[name].passed]
    return {
        "pass": not failed,
        "category": failed[0] if failed else "pass",
        "checks": {name: {"pass": c.passed, "detail": c.detail} for name, c in checks.items()},
        "measured": {"solids": [measured(s) for s in variant.solids]},
    }


def measured(solid: Solid) -> dict[str, object]:
    return {
        "volume": round(solid.volume, 3),
        "bbox": [[round(v, 3) for v in solid.lo], [round(v, 3) for v in solid.hi]],
    }


def run_checks(start: Model, reference: Model, variant: Model) -> dict[CheckName, Check]:
    kept, target, removed = split_reference(start, reference)
    found, extra = match(reference.surfaces, variant.surfaces)
    missing = [s for s, hit in zip(reference.surfaces, found, strict=True) if hit is None]
    left_over = [s for s in removed if any(h is not None for h in match([s], extra)[0])]
    return {
        "solids": solids_check(reference, variant),
        "interference": interference_check(variant),
        "target": surfaces_check(
            [s for s in missing if s in target], "requested change missing", left_over
        ),
        "untouched": surfaces_check([s for s in missing if s in kept], "untouched feature lost"),
        "shape": shape_check(reference, variant, extra),
    }


def split_reference(
    start: Model, reference: Model
) -> tuple[set[Surface], set[Surface], list[Surface]]:
    """Split reference surfaces into kept and target, and list the start's removed ones."""
    found, removed = match(reference.surfaces, start.surfaces)
    kept = {s for s, hit in zip(reference.surfaces, found, strict=True) if hit is not None}
    target = set(reference.surfaces) - kept
    return kept, target, removed


def match(
    wanted: Sequence[Surface], offered: Sequence[Surface]
) -> tuple[list[Surface | None], list[Surface]]:
    """Pair each wanted surface with an equal offered one, each used at most once.

    Returns the partner of each wanted surface, or None, and the offered surfaces left over.
    """
    pool = sorted(offered, key=lambda s: s.area)
    areas = [s.area for s in pool]
    used = [False] * len(pool)
    partners: list[Surface | None] = []
    for want in wanted:
        tol = area_tol(want.area)
        lo = bisect.bisect_left(areas, want.area - tol)
        hi = bisect.bisect_right(areas, want.area + tol)
        hit = next((i for i in range(lo, hi) if not used[i] and same(want, pool[i])), None)
        if hit is not None:
            used[hit] = True
        partners.append(None if hit is None else pool[hit])
    return partners, [s for s, u in zip(pool, used, strict=True) if not u]


def area_tol(area: float) -> float:
    return AREA_ABS_TOL + AREA_REL_TOL * area


def same(a: Surface, b: Surface) -> bool:
    return (
        a.kind == b.kind
        and len(a.params) == len(b.params)
        and all(abs(x - y) <= PARAM_TOL for x, y in zip(a.params, b.params, strict=True))
        and abs(a.area - b.area) <= area_tol(a.area)
    )


def surfaces_check(missing: list[Surface], what: str, left: Sequence[Surface] = ()) -> Check:
    problems = [f"{what}: {s.describe()}" for s in missing]
    problems += [f"removed feature still present: {s.describe()}" for s in left]
    return Check(not problems, summary(problems))


def summary(problems: list[str]) -> str:
    more = f" (+{len(problems) - SHOWN} more)" if len(problems) > SHOWN else ""
    return "; ".join(problems[:SHOWN]) + more


def solids_check(reference: Model, variant: Model) -> Check:
    problems: list[str] = []
    want, got = len(reference.solids), len(variant.solids)
    if got != want:
        problems.append(f"{got} solids, want {want}")
    problems += [f"solid {s.index} fails BRepCheck" for s in variant.solids if not s.valid]
    problems += [f"solid {s.index} is not closed" for s in variant.solids if not s.closed]
    return Check(not problems, summary(problems))


def interference_check(variant: Model) -> Check:
    problems = [
        f"solids {a.index} and {b.index} overlap by {v:.3f} mm3"
        for i, a in enumerate(variant.solids)
        for b in variant.solids[i + 1 :]
        if (v := common_volume(a, b)) > INTERFERENCE_TOL
    ]
    return Check(not problems, summary(problems))


def shape_check(reference: Model, variant: Model, extra: list[Surface]) -> Check:
    problems = [f"unexpected surface: {s.describe()}" for s in extra]
    unmatched = list(variant.solids)
    for want in reference.solids:
        hit = next((s for s in unmatched if same_solid(want, s)), None)
        if hit is None:
            problems.append(
                f"no solid matches reference solid {want.index} "
                f"(volume {want.volume:.2f}, bbox {fmt(want.lo)} to {fmt(want.hi)})"
            )
        else:
            unmatched.remove(hit)
    return Check(not problems, summary(problems))


def same_solid(a: Solid, b: Solid) -> bool:
    volume_ok = abs(a.volume - b.volume) <= VOLUME_ABS_TOL + VOLUME_REL_TOL * abs(a.volume)
    corners = [*a.lo, *a.hi], [*b.lo, *b.hi]
    return volume_ok and all(abs(x - y) <= BBOX_TOL for x, y in zip(*corners, strict=True))


def fmt(v: tuple[float, float, float]) -> str:
    return "(" + ", ".join(f"{c:.2f}" for c in v) + ")"


if __name__ == "__main__":
    print(json.dumps(grade(sys.argv[1], Path(sys.argv[2]))))
