import json
from pathlib import Path

import pytest

from cad.sandbox import container, stage
from cad.sandbox.container import Job
from cad.sandbox.image import ANALYSIS, current_image, image_tag

pytestmark = pytest.mark.docker

PROBE = """import json, os, sys
saved = os.dup(1)
os.dup2(2, 1)
sys.path.insert(0, "/opt/trusted")
from build123d import Align, Box, Cylinder, Pos, Rot
from cad.checks.container.anchors import resolve
from cad.checks.container.regions import Resolved
from cad.checks.container.kernel import ocp_kernel

plate = (
    Pos(10, 0, 0) * Box(80, 20, 8)
    - Pos(-20, 0, 0) * Cylinder(2.75, 8)
    - Pos(-20, 0, 2) * Cylinder(5, 4)
    - Pos(20, 0, 0) * Cylinder(2.75, 8)
    + Pos(0, 0, 4) * Cylinder(2.75, 6)
)
kernel = ocp_kernel()
case = {
    "support": {"kind": "holes", "count": 2, "diameter_mm": 5.5},
    "load": {
        "kind": "far_end",
        "force_n": 49.0,
        "direction": {"kind": "across", "axis": "hole_axis"},
    },
}
found = []
for part in (plate, Pos(100, -40, 7) * Rot(30, 50, 70) * plate):
    shape = part.wrapped
    resolved = resolve(case, kernel.faces(shape), kernel.inertia(shape))
    assert isinstance(resolved, Resolved), resolved
    (candidate,) = resolved.candidates
    found.append({
        "radii": sorted(round(bore.radius, 9) for bore in candidate.support.patches),
        "lengths": sorted(round(bore.t1 - bore.t0, 9) for bore in candidate.support.patches),
        "basis": len(resolved.basis),
    })

MIN = (Align.MIN, Align.MIN, Align.MIN)
l_bracket = Pos(0, 0, -45) * Box(5, 30, 50, align=MIN) + Box(100, 30, 5, align=MIN)
t_arm = (
    Pos(0, -20, -20) * Box(4, 40, 40, align=MIN)
    + Pos(0, -10, 17) * Box(100, 20, 3, align=MIN)
    + Pos(0, -1.5, 2) * Box(100, 3, 15, align=MIN)
)
ends = {
    "support": {"kind": "flat_end"},
    "load": {"kind": "far_end", "force_n": 20.0, "direction": {"kind": "any"}},
}


def fingerprint(region):
    (patch,) = region.patches
    return [round(c, 6) for c in (*region.centroid, *patch.normal)]


def frame_free(candidate, inertia):
    (support,), (load,) = candidate.support.patches, candidate.load.patches
    gap = [a - b for a, b in zip(candidate.load.centroid, candidate.support.centroid)]
    lever = [a - b for a, b in zip(inertia.center, candidate.support.centroid)]
    return [
        round(sum(g * g for g in gap) ** 0.5, 6),
        round(sum(a * b for a, b in zip(support.normal, load.normal)), 6),
        round(sum(v * v for v in lever) ** 0.5, 6),
    ]


faced = {}
for name, part in (("l_bracket", l_bracket), ("t_arm", t_arm)):
    seen = []
    for placed in (part, Pos(100, -40, 7) * Rot(30, 50, 70) * part):
        shape = placed.wrapped
        inertia = kernel.inertia(shape)
        resolved = resolve(ends, kernel.faces(shape), inertia)
        assert isinstance(resolved, Resolved), resolved
        seen.append({
            "frame_free": sorted(frame_free(c, inertia) for c in resolved.candidates),
            "faces": sorted(
                [fingerprint(c.support), fingerprint(c.load)] for c in resolved.candidates
            ),
        })
    faced[name] = seen
os.write(saved, json.dumps({"plate": found, "ends": faced}).encode())
"""


def test_anchors_resolve_the_same_in_the_analysis_image_whatever_the_frame(
    tmp_path: Path,
) -> None:
    staged = stage.materialize(stage.read_sources("cad.checks.container.anchors"), tmp_path)
    image = current_image(image_tag(ANALYSIS))
    job = Job(
        "check",
        image,
        ("python", "-I", "-c", PROBE),
        b"",
        (container.ReadOnlyMount(staged, stage.TARGET),),
    )
    ran = container.run(job)
    assert ran.state.ExitCode == 0, ran.attended.output
    assert isinstance(ran.attended.report, bytes)
    report = json.loads(ran.attended.report)
    plain, turned = report["plate"]
    assert plain == turned
    assert plain == {"radii": [2.75, 2.75], "lengths": [4.0, 8.0], "basis": 2}
    for name, (plain_ends, turned_ends) in report["ends"].items():
        flat = [value for row in plain_ends["frame_free"] for value in row]
        turned_flat = [value for row in turned_ends["frame_free"] for value in row]
        assert flat == pytest.approx(turned_flat, abs=1e-5), name
    assert report["ends"]["l_bracket"][0]["faces"] == [
        [[0, 15, -20, -1, 0, 0], [100, 15, 2.5, 1, 0, 0]],
        [[100, 15, 2.5, 1, 0, 0], [0, 15, -20, -1, 0, 0]],
    ]
    t_faces = report["ends"]["t_arm"][0]["faces"]
    assert [[support[0], support[3], load[0], load[3]] for support, load in t_faces] == [
        [0, -1, 100, 1],
        [100, 1, 0, -1],
    ]
