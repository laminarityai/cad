"""Runs in the analysis image, on one BREP on stdin and a job as JSON in argv. Mode `faces` gives
the kernel's faces in explorer order and the surface share of every candidate the reviewed and
described cases resolve to. Mode `placed` gives each placement's candidates with the mirror gate's
additions and, when asked, today's `fea` check on them."""

import json
import math
import sys
from typing import NotRequired, TypedDict, cast

from placed import ANY_WAY, CandidateWire, mirrored, region, share, solved

from cad.checks.container import anchors, terms
from cad.checks.container.features import Geometry, geometry
from cad.checks.container.kernel import Curved, Flat, Kernel, Round, Shape, Unreadable, ocp_kernel
from cad.checks.container.regions import Candidate, Disc, FarFrom, Region, Resolved
from cad.checks.container.wire import LoadCaseWire, ValueWire


class LabelledCase(TypedDict):
    label: str
    wire: LoadCaseWire


class PlacementJob(TypedDict):
    label: str
    candidates: list[CandidateWire]
    solve: bool


class Job(TypedDict):
    mode: str
    cases: NotRequired[list[LabelledCase]]
    placements: NotRequired[list[PlacementJob]]
    values: NotRequired[dict[str, ValueWire]]
    force_n: NotRequired[float]


def main() -> None:
    job = cast(Job, json.loads(sys.argv[1]))
    kernel = ocp_kernel()
    brep = sys.stdin.buffer.read()
    shape = kernel.read_brep(brep)
    assert not isinstance(shape, Unreadable), shape.reason
    part = geometry(kernel, shape)
    if job["mode"] == "faces":
        out: object = faces(part, job.get("cases", []))
    else:
        out = [placement(kernel, brep, shape, part, one, job) for one in job.get("placements", [])]
    sys.stdout.write(json.dumps(out))


def faces(part: Geometry, cases: list[LabelledCase]) -> dict[str, object]:
    rows: list[object] = []
    for face in part.faces:
        kind = {Flat: "flat", Round: "round", Curved: "curved"}[type(face.surface)]
        rows.append([kind, face.area, *face.centroid])
    return {
        "faces": rows,
        "curved": sum(isinstance(face.surface, Curved) for face in part.faces),
        "cases": [resolved_shares(part, one) for one in cases],
    }


def resolved_shares(part: Geometry, labelled: LabelledCase) -> dict[str, object]:
    resolved = anchors.resolve(terms.of_wire(labelled["wire"]), part)
    if not isinstance(resolved, Resolved):
        return {"label": labelled["label"], "unresolved": resolved.reason}
    return {
        "label": labelled["label"],
        "candidates": [
            {"support": region_share(part, c.support), "load": region_share(part, c.load)}
            for c in resolved.candidates
        ],
    }


def region_share(part: Geometry, found: Region | FarFrom) -> dict[str, object]:
    if isinstance(found, FarFrom):
        return {"band": True}
    discs = [p for p in found.patches if isinstance(p, Disc)]
    total = sum(face.area for face in part.faces)
    covered = (
        sum(math.pi * d.radius**2 for d in discs) / total if discs else share(part, found.faces)
    )
    return {"faces": sorted(found.faces), "share": covered, "disc": bool(discs)}


def placement(
    kernel: Kernel, brep: bytes, shape: Shape, part: Geometry, one: PlacementJob, job: Job
) -> dict[str, object]:
    pairs: dict[tuple[tuple[int, ...], tuple[int, ...]], tuple[str, bool]] = {}
    for wire in one["candidates"]:
        found = mirrored(part, frozenset(wire["support"]), frozenset(wire["load"]))
        for k, (s, ld) in enumerate(found):
            key = (tuple(sorted(s.faces)), tuple(sorted(ld.faces)))
            pairs.setdefault(key, ("code" if k == 0 else "mirror", wire["middle"]))
    listed: list[dict[str, object]] = []
    candidates: list[Candidate] = []
    unresolved: list[str] = []
    for (support, load), (source, middle) in pairs.items():
        held, loaded = region(part, support, False), region(part, load, middle)
        listed.append({
            "support": list(support),
            "load": list(load),
            "source": source,
            "support_share": share(part, frozenset(support)),
            "load_share": share(part, frozenset(load)),
            "kinds": [_kind(part, i) for i in (*support, *load)],
        })  # fmt: skip
        if not isinstance(held, Region) or not isinstance(loaded, Region):
            unresolved.extend(r.reason for r in (held, loaded) if not isinstance(r, Region))
            continue
        candidates.append(Candidate(held, loaded, ANY_WAY))
    out: dict[str, object] = {
        "label": one["label"],
        "code": len(one["candidates"]),
        "candidates": listed,
        "over_limit": len(pairs) > anchors.CANDIDATE_LIMIT,
        "unresolved": unresolved,
    }
    if one["solve"] and not unresolved and not out["over_limit"]:
        values, force_n = job.get("values", {}), job.get("force_n", 0.0)
        finding, seconds = solved(kernel, brep, shape, candidates, values, force_n)
        out["finding"] = finding
        out["seconds"] = seconds
    return out


def _kind(part: Geometry, i: int) -> str:
    return type(part.faces[i].surface).__name__.lower()


if __name__ == "__main__":
    main()
