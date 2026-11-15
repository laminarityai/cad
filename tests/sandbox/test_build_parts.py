"""A build reads the supplied parts it names from stdin, after its code (ADR-0012)."""

import hashlib
import json
from pathlib import Path

import pytest

from cad.sandbox.builder import Supplied, build_job
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import BuildFailed, Built, PartPlacement, PartUse
from cad.variants.entry import open_entry
from cad.variants.store import build_variant
from tests.support.solids import box, brep_bytes, rod

WHEEL_BREP = brep_bytes(rod(20, 10, (0, 0, 0)))
BLOCK_BREP = brep_bytes(box(4, 5, 6))
WHEEL_ID = "part-" + hashlib.sha256(WHEEL_BREP).hexdigest()[:16]
SPOTS = (PartPlacement(at=(30, 20, 0)), PartPlacement(at=(-30, 20, 0), rotate=(0, 0, 90)))
WHEEL = Supplied(
    PartUse(
        part_id=WHEEL_ID,
        project="p-0123456789abcdef",
        brep_sha256=hashlib.sha256(WHEEL_BREP).hexdigest(),
        placements=SPOTS,
    ),
    WHEEL_BREP,
)
BLOCK = Supplied(
    PartUse(
        part_id="part-" + hashlib.sha256(BLOCK_BREP).hexdigest()[:16],
        project="p-0123456789abcdef",
        brep_sha256=hashlib.sha256(BLOCK_BREP).hexdigest(),
    ),
    BLOCK_BREP,
)
PLATE = f"""
from build123d import *
wheel = part("{WHEEL_ID}")
size = wheel.bounding_box().size
print("wheel", round(size.X, 3), round(size.Y, 3), round(size.Z, 3))
plate = Box(100, 60, 5)
for spot in placed("{WHEEL_ID}"):
    print("spot", tuple(round(value, 3) for value in spot.position))
    plate -= spot * Cylinder(4, 10)
result = plate
"""
FUSED = f"""
from build123d import *
plate = Box(100, 60, 5)
for spot in placed("{WHEEL_ID}"):
    plate += spot * part("{WHEEL_ID}")
result = plate
"""
FUSED_UNPLACED = """
from build123d import *
result = Box(20, 20, 2, align=Align.MIN) + part("%s")
"""
ALONE = """
from build123d import *
plate = Box(100, 60, 5)
for spot in (Location((30, 20, 0), (0, 0, 0)), Location((-30, 20, 0), (0, 0, 90))):
    plate -= spot * Cylinder(4, 10)
result = plate
"""


def test_the_parts_follow_the_code_on_stdin_in_the_order_argv_lists_them() -> None:
    job = build_job("x = 1\n", "sha256:abc", 60, (WHEEL, BLOCK))
    assert job.stdin == b"x = 1\n" + WHEEL_BREP + BLOCK_BREP
    assert json.loads(job.command[-1]) == [
        {
            "id": WHEEL_ID,
            "size": len(WHEEL_BREP),
            "placements": [
                {"at": [30.0, 20.0, 0.0], "rotate": [0.0, 0.0, 0.0]},
                {"at": [-30.0, 20.0, 0.0], "rotate": [0.0, 0.0, 90.0]},
            ],
        },
        {"id": BLOCK.use.part_id, "size": len(BLOCK_BREP), "placements": []},
    ]
    assert job.mounts == ()


@pytest.mark.docker
def test_build_code_reads_a_part_in_its_own_frame_and_places_each_copy(tmp_path: Path) -> None:
    result = build_variant(PLATE, tmp_path, parts=(WHEEL, BLOCK))
    assert isinstance(result.outcome, Built), result.output
    assert "wheel 40.0 40.0 10.0\n" in result.output
    assert "spot (30.0, 20.0, 0.0)\nspot (-30.0, 20.0, 0.0)\n" in result.output
    held = open_entry(tmp_path, result.variant_id, image_tag(BUILD))
    assert held.parts == (WHEEL.use, BLOCK.use)


@pytest.mark.docker
def test_a_part_the_build_was_not_sent_fails_the_build_with_its_id(tmp_path: Path) -> None:
    result = build_variant(PLATE, tmp_path, parts=(BLOCK,))
    assert isinstance(result.outcome, BuildFailed)
    assert f"{WHEEL_ID!r} is not a part this build reads" in result.outcome.error


@pytest.mark.docker
def test_the_stored_shape_is_the_agents_body_alone_whatever_parts_it_placed(
    tmp_path: Path,
) -> None:
    placed = build_variant(PLATE, tmp_path, parts=(WHEEL,))
    alone = build_variant(ALONE, tmp_path)
    assert placed.variant_id != alone.variant_id
    shapes = {
        open_entry(tmp_path, one.variant_id, image_tag(BUILD)).brep for one in (placed, alone)
    }
    assert len(shapes) == 1


@pytest.mark.docker
def test_a_placed_copy_fused_into_result_fails_the_build_and_names_it(tmp_path: Path) -> None:
    result = build_variant(FUSED, tmp_path, parts=(WHEEL,))
    assert isinstance(result.outcome, BuildFailed), result.output
    assert result.outcome.error.startswith(
        f"result holds 100% of supplied part {WHEEL_ID} at placement 1 (30, 20, 0)"
    )
    assert "Keep the part out of result" in result.outcome.error


@pytest.mark.docker
def test_a_part_fused_into_result_in_its_own_frame_fails_the_build(tmp_path: Path) -> None:
    code = FUSED_UNPLACED % BLOCK.use.part_id
    result = build_variant(code, tmp_path, parts=(BLOCK,))
    assert isinstance(result.outcome, BuildFailed), result.output
    assert f"supplied part {BLOCK.use.part_id} in its own frame" in result.outcome.error
