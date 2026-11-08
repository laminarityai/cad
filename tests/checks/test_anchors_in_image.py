import json
from pathlib import Path

from cad.sandbox import container, stage
from cad.sandbox.container import Job
from cad.sandbox.image import ANALYSIS, current_image, image_tag

PROBE = """import json, os, sys
saved = os.dup(1)
os.dup2(2, 1)
sys.path.insert(0, "/opt/trusted")
from build123d import Box, Cylinder, Pos, Rot
from cad.checks.container.anchors import Resolved, resolve
from cad.checks.container.kernel import ocp_kernel

plate = (
    Box(60, 20, 8)
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
os.write(saved, json.dumps(found).encode())
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
    plain, turned = json.loads(ran.attended.report)
    assert plain == turned
    assert plain == {"radii": [2.75, 2.75], "lengths": [4.0, 8.0], "basis": 2}
