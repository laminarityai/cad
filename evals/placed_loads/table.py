"""The tables `measure.py table` prints, from the rows `faces` and `solve` wrote."""

import math
from collections.abc import Sequence
from typing import Final, cast

from cad.checks.container.vectors import Point, add, dot, norm, scale, sub

type Row = dict[str, object]

STUCK: Final = frozenset({
    "cantilever_bar", "l_plain", "l_holes", "l_filleted", "hook", "t_arm", "t_arm_flat_end",
    "truss_arm", "equal_angle", "sb_gusset", "sb_arm", "sb_l_bracket",
})  # fmt: skip
"""The 12 corpus parts the reviewed phrases leave stuck (fea-described-loads.md)."""
DEFLECTION_LIMIT_MM: Final = 2.0
"""The corpus requirement: the tip moves at most 2 mm."""


def tables(faces: Sequence[Row], solves: Sequence[Row]) -> str:
    parts = (decided(solves), order(faces), shares(faces), mirrors(faces), curved(faces))
    return "\n\n".join(parts)


def decided(solves: Sequence[Row]) -> str:
    lines = [
        f"| Placement | Check verdict | Max displacement mm | Safety factor "
        f"| Deflection at most {DEFLECTION_LIMIT_MM:g} mm | Candidates | Solve s | Reason |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in solves:
        listed = _rows(row["candidates"])
        finding = cast(Row, row.get("finding", {}))
        verdict = str(finding.get("verdict", "not solved"))
        measured = {
            str(m["name"]): cast(float, m["magnitude"])
            for m in cast(list[Row], finding.get("measured", []))
        }
        shown = measured.get("max_displacement")
        within = (
            "unknown"
            if verdict == "unknown" or shown is None
            else ("pass" if shown <= DEFLECTION_LIMIT_MM else "fail")
        )
        factor = measured.get("safety_factor")
        reason = "" if verdict == "pass" else str(finding.get("reason", ""))
        lines.append(
            f"| {row['label']} | {verdict} | {_number(shown)} | {_number(factor)} | {within} "
            f"| {len(listed)} | {_seconds(row)} | {reason} |"
        )
    return "\n".join(lines)


def order(faces: Sequence[Row]) -> str:
    lines = [
        "| Part | Faces | Build = analysis | Max area diff | Max centroid diff mm "
        "| Turned keeps order | Max turned centroid diff mm | Placement indices kept |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in faces:
        build = _lists(cast(Row, row["side"])["faces"])
        kernel = _lists(cast(Row, row["kernel"])["faces"])
        area, at = _diff(build, [k[1:] for k in kernel])
        same = len(build) == len(kernel)
        turned = _turned(row, kernel)
        lines.append(
            f"| {row['part']} | {len(kernel)} | {_yes(same)} | {area:.1e} | {at:.1e} "
            f"| {turned[0]} | {turned[1]} | {turned[2]} |"
        )
    return "\n".join(lines)


def shares(faces: Sequence[Row]) -> str:
    lines = [
        "| Part | Case | Candidates | Largest support share | Largest load share |",
        "|---|---|---|---|---|",
    ]
    best = 0.0
    for row in faces:
        for one in _rows(cast(Row, row["kernel"])["cases"]):
            if "unresolved" in one:
                lines.append(f"| {row['part']} | {one['label']} | unresolved | | |")
                continue
            listed = _rows(one["candidates"])
            held = max(cast(float, cast(Row, c["support"])["share"]) for c in listed)
            loaded = [cast(Row, c["load"]) for c in listed]
            load = max((cast(float, ld["share"]) for ld in loaded if "share" in ld), default=0.0)
            band = " (band)" if any("band" in ld for ld in loaded) else ""
            best = max(best, held, load)
            lines.append(
                f"| {row['part']} | {one['label']} | {len(listed)} "
                f"| {held:.1%} | {load:.1%}{band} |"
            )
    lines.append(f"\nLargest share of any reviewed or described region: {best:.1%}.")
    return "\n".join(lines)


def mirrors(faces: Sequence[Row]) -> str:
    lines = [
        "| Placement | From code | Mirror adds | Total | Over 4 | Support share | Load share "
        "| Surfaces |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in faces:
        for one in _rows(row.get("placed", [])):
            listed = _rows(one["candidates"])
            code = sum(c["source"] == "code" for c in listed)
            held = max(cast(float, c["support_share"]) for c in listed)
            load = max(cast(float, c["load_share"]) for c in listed)
            kinds = sorted({k for c in listed for k in cast(list[str], c["kinds"])})
            lines.append(
                f"| {one['label']} | {code} | {len(listed) - code} | {len(listed)} "
                f"| {'yes' if one['over_limit'] else 'no'} | {held:.1%} | {load:.1%} "
                f"| {', '.join(kinds)} |"
            )
    return "\n".join(lines)


def curved(faces: Sequence[Row]) -> str:
    stuck = [row for row in faces if row["part"] in STUCK]
    lines = ["| Stuck part | Faces | Curved faces |", "|---|---|---|"]
    for row in stuck:
        kernel = cast(Row, row["kernel"])
        lines.append(f"| {row['part']} | {len(_lists(kernel['faces']))} | {kernel['curved']} |")
    having = sum(cast(int, cast(Row, row["kernel"])["curved"]) > 0 for row in stuck)
    lines.append(f"\nStuck parts with any curved face: {having} of {len(stuck)}.")
    return "\n".join(lines)


def _turned(row: Row, kernel: Sequence[list[object]]) -> tuple[str, str, str]:
    if "turned_kernel" not in row:
        return ("turn failed", "", "")
    motion = cast(Row, row["motion"])
    axis = cast(Point, tuple(cast(list[float], motion["axis"])))
    radians = math.radians(cast(float, motion["degrees"]))
    offset = cast(Point, tuple(cast(list[float], motion["offset"])))
    turned = _lists(cast(Row, row["turned_kernel"])["faces"])
    moved = [
        [k[0], k[1], *add(_rotate(cast(Point, tuple(k[2:5])), axis, radians), offset)]
        for k in kernel
    ]
    kinds = [t[0] for t in turned] == [m[0] for m in moved]
    area, at = _diff([t[1:] for t in turned], [m[1:] for m in moved])
    side = _candidates(row["side"])
    kept = side == _candidates(row["turned_side"]) if side else "no placement"
    within = area < 1e-6 and at < 1e-3
    return (_yes(kinds and within), f"{at:.1e}", kept if isinstance(kept, str) else _yes(kept))


def _candidates(side: object) -> dict[str, object]:
    placements = cast(dict[str, Row], cast(Row, side)["placements"])
    return {label: one.get("candidates", one.get("failed")) for label, one in placements.items()}


def _rotate(point: Point, axis: Point, radians: float) -> Point:
    """Rodrigues' rotation of the point about the unit axis through the origin."""
    c, s = math.cos(radians), math.sin(radians)
    cross: Point = (
        axis[1] * point[2] - axis[2] * point[1],
        axis[2] * point[0] - axis[0] * point[2],
        axis[0] * point[1] - axis[1] * point[0],
    )
    return add(add(scale(point, c), scale(cross, s)), scale(axis, dot(axis, point) * (1 - c)))


def _diff(a: Sequence[Sequence[object]], b: Sequence[Sequence[object]]) -> tuple[float, float]:
    """The largest relative area difference and centroid distance between rows at one index, or
    infinity when the counts differ."""
    if len(a) != len(b):
        return math.inf, math.inf
    pairs = list(zip(a, b, strict=True))
    area = max(abs(cast(float, x[0]) / cast(float, y[0]) - 1) for x, y in pairs)
    at = max(norm(sub(cast(Point, tuple(x[1:4])), cast(Point, tuple(y[1:4])))) for x, y in pairs)
    return area, at


def _number(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _seconds(row: Row) -> str:
    return f"{cast(float, row['seconds']):.0f}" if "seconds" in row else ""


def _rows(value: object) -> list[Row]:
    return cast(list[Row], value)


def _lists(value: object) -> list[list[object]]:
    return cast(list[list[object]], value)


def _yes(value: bool) -> str:
    return "yes" if value else "NO"
