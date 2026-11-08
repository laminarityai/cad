import json

import pytest

from cad.checks.report import IMAGE_TAG
from cad.sandbox import container
from cad.sandbox.container import Job
from cad.sandbox.image import current_image

PROBE = r"""
import json, subprocess
from pathlib import Path

import gmsh

gmsh.initialize(["-nt", "1"])
gmsh.option.setNumber("General.Terminal", 0)
gmsh.option.setNumber("Mesh.Algorithm3D", 1)
gmsh.option.setNumber("Mesh.RandomSeed", 1)
gmsh.option.setNumber("Mesh.MeshSizeMax", 3.0)
gmsh.model.occ.addBox(0, 0, 0, 10, 10, 10)
gmsh.model.occ.synchronize()
gmsh.model.mesh.generate(3)
nodes = len(gmsh.model.mesh.getNodes()[0])
gmsh.finalize()

Path("tet.inp").write_text('''*NODE, NSET=NALL
1, 0, 0, 0
2, 1, 0, 0
3, 0, 1, 0
4, 0, 0, 1
*ELEMENT, TYPE=C3D4, ELSET=EALL
1, 1, 2, 3, 4
*BOUNDARY
1, 1, 3
2, 2, 3
3, 3, 3
*MATERIAL, NAME=STEEL
*ELASTIC
210000, 0.3
*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL
*STEP
*STATIC
*CLOAD
4, 3, 1.0
*NODE PRINT, NSET=NALL
U
*END STEP
''')
ccx = subprocess.run(["ccx", "-i", "tet"], capture_output=True, text=True, check=False)
node_4 = [line.split() for line in Path("tet.dat").read_text().splitlines()
          if line.split()[:1] == ["4"]]

corners = [(x, y, z) for x in (0, 20) for y in (0, 20) for z in (0, 20)]
quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
facets = [
    "facet normal 0 0 0\nouter loop\n"
    + "".join(f"vertex {' '.join(map(str, corners[i]))}\n" for i in triangle)
    + "endloop\nendfacet\n"
    for a, b, c, d in quads
    for triangle in ((a, b, c), (a, c, d))
]
Path("cube.stl").write_text("solid cube\n" + "".join(facets) + "endsolid cube\n")
sliced = subprocess.run(
    ["prusa-slicer", "--export-gcode", "--output", "cube.gcode", "cube.stl"],
    capture_output=True, text=True, check=False,
)
header = [line for line in Path("cube.gcode").read_text().splitlines()
          if line.startswith("; estimated printing time")] if sliced.returncode == 0 else []

print(json.dumps({
    "gmsh_nodes": nodes,
    "ccx_exit": ccx.returncode,
    "ccx_u3_node_4": float(node_4[0][3]) if node_4 else None,
    "slicer_exit": sliced.returncode,
    "slicer_tail": sliced.stderr[-400:],
    "print_time": header,
}))
"""


@pytest.fixture(scope="module")
def probed() -> dict[str, object]:
    job = Job("check", current_image(IMAGE_TAG), ("python", "-I", "-c", PROBE), b"")
    ran = container.run(job)
    assert ran.state.ExitCode == 0, ran.attended.output
    assert isinstance(ran.attended.report, bytes)
    return json.loads(ran.attended.report)


def test_gmsh_meshes_a_box_in_the_check_sandbox(probed: dict[str, object]) -> None:
    assert isinstance(probed["gmsh_nodes"], int) and probed["gmsh_nodes"] > 8


def test_calculix_solves_one_tetrahedron_in_the_check_sandbox(probed: dict[str, object]) -> None:
    assert probed["ccx_exit"] == 0
    assert isinstance(probed["ccx_u3_node_4"], float) and probed["ccx_u3_node_4"] > 0


def test_the_slicer_slices_a_cube_with_no_display(probed: dict[str, object]) -> None:
    assert probed["slicer_exit"] == 0, probed["slicer_tail"]
    assert probed["print_time"] != []
