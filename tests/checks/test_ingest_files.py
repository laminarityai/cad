import base64
import importlib
from typing import Any

import pytest

from cad.checks.container.ingest import ReadAs, answer, facts
from cad.checks.container.kernel import Kernel, Unreadable, ocp_kernel
from cad.checks.container.whole_solids import unmeasurable
from tests.support.part_files import named_step_bytes, step_bytes, stl_bytes
from tests.support.solids import (
    box,
    box_face,
    box_shell,
    brep_bytes,
    compound,
    cut,
    inside_out,
    loosened,
    through_hole,
)

STEP: ReadAs = {"format": "step", "scale": 1.0}
BREP: ReadAs = {"format": "brep", "scale": 1.0}
MM: ReadAs = {"format": "stl", "scale": 1.0}
INCHES: ReadAs = {"format": "stl", "scale": 25.4}


@pytest.fixture(scope="module")
def kernel() -> Kernel:
    return ocp_kernel()


def part(kernel: Kernel, read_as: ReadAs, data: bytes) -> dict[str, Any]:
    found = facts(kernel, read_as, data)
    assert found["kind"] == "part", found
    return dict(found)


def test_a_step_of_a_plate_with_a_through_hole_reports_the_hole_and_the_box(kernel: Kernel) -> None:
    plate = cut(box(40, 20, 10, at=(5, 6, 7)), through_hole(6, 15, 16, depth=10))
    found = part(kernel, STEP, step_bytes(plate))
    assert found["solids"] == 1
    assert found["box_min"] == pytest.approx([5, 6, 7], abs=1e-6)
    assert found["box_max"] == pytest.approx([45, 26, 17], abs=1e-6)
    assert len(found["holes"]) == 1
    hole = found["holes"][0]
    assert hole["diameter_mm"] == pytest.approx(6, abs=1e-6)
    assert hole["solid"] == 0
    assert abs(hole["axis"][2]) == pytest.approx(1, abs=1e-9)
    assert found["left_out"] == {"bodies": 1, "unreadable": 0, "loose": 0}


def test_a_flat_reports_its_normal_area_and_centroid(kernel: Kernel) -> None:
    found = part(kernel, STEP, step_bytes(box(40, 20, 10)))
    largest = found["flats"][0]
    assert largest["area_mm2"] == pytest.approx(800, rel=1e-6)
    assert [abs(n) for n in largest["normal"]] == pytest.approx([0, 0, 1], abs=1e-9)
    assert largest["centroid"][:2] == pytest.approx([20, 10], abs=1e-6)


def test_a_step_in_inches_comes_back_in_millimetres(kernel: Kernel) -> None:
    plate = cut(box(50.8, 25.4, 12.7), through_hole(6.35, 25.4, 12.7, depth=12.7))
    in_mm = part(kernel, STEP, step_bytes(plate, "MM"))
    in_inches = part(kernel, STEP, step_bytes(plate, "INCH"))
    assert in_inches["volume_mm3"] == pytest.approx(in_mm["volume_mm3"], rel=1e-9)
    assert in_inches["box_max"] == pytest.approx([50.8, 25.4, 12.7], abs=1e-6)
    assert in_inches["holes"][0]["diameter_mm"] == pytest.approx(6.35, abs=1e-6)


def test_a_step_with_two_solids_and_an_open_shell_keeps_the_two(kernel: Kernel) -> None:
    body = compound(box(10, 10, 10), box(5, 5, 5, at=(20, 0, 0)), box_shell(3, 3, 3))
    found = part(kernel, STEP, step_bytes(body))
    assert found["solids"] == 2
    assert found["volume_mm3"] == pytest.approx(1125, rel=1e-9)
    assert found["left_out"] == {"bodies": 3, "unreadable": 1, "loose": 0}


def test_a_step_that_is_only_an_open_shell_has_no_solid_to_read(kernel: Kernel) -> None:
    found = facts(kernel, STEP, step_bytes(box_shell(10, 10, 10)))
    assert found == {
        "kind": "refused",
        "reason": "the file has no solid that can be read: 1 solids or shells, none readable",
    }


def test_a_named_step_product_is_reported(kernel: Kernel) -> None:
    assert part(kernel, STEP, named_step_bytes(box(10, 10, 10), "Bracket"))["names"] == ["Bracket"]


def test_a_step_nobody_named_reports_no_names(kernel: Kernel) -> None:
    assert part(kernel, STEP, step_bytes(box(10, 10, 10)))["names"] == []


@pytest.mark.parametrize("read_as", [STEP, MM], ids=["step", "stl"])
@pytest.mark.parametrize("data", [b"", b"garbage bytes, not a model", bytes(range(256)) * 20])
def test_bytes_that_are_not_the_format_are_refused(
    kernel: Kernel, read_as: ReadAs, data: bytes
) -> None:
    found = dict(facts(kernel, read_as, data))
    kind = "STEP" if read_as["format"] == "step" else "STL"
    assert found["kind"] == "refused"
    assert str(found["reason"]).startswith(f"the {kind} file cannot be read"), found


@pytest.mark.parametrize("ascii_file", [False, True], ids=["binary", "ascii"])
def test_an_stl_box_is_a_solid_of_the_right_size(kernel: Kernel, ascii_file: bool) -> None:
    found = part(kernel, MM, stl_bytes(box(30, 10, 20, at=(1, 2, 3)), ascii_file=ascii_file))
    assert found["solids"] == 1
    assert found["volume_mm3"] == pytest.approx(6000, rel=1e-4)
    assert found["box_min"] == pytest.approx([1, 2, 3], abs=1e-4)
    assert found["box_max"] == pytest.approx([31, 12, 23], abs=1e-4)
    assert found["names"] == []
    assert found["left_out"] == {"bodies": 1, "unreadable": 0, "loose": 0}


def test_an_stl_in_inches_is_scaled_by_25_4(kernel: Kernel) -> None:
    data = stl_bytes(box(30, 10, 20))
    in_mm = part(kernel, MM, data)["volume_mm3"]
    in_inches = part(kernel, INCHES, data)["volume_mm3"]
    assert in_inches == pytest.approx(in_mm * 25.4**3, rel=1e-9)


def test_an_stl_has_flats_but_no_holes_because_it_has_only_triangles(kernel: Kernel) -> None:
    plate = cut(box(40, 20, 10), through_hole(6, 20, 10, depth=10))
    found = part(kernel, MM, stl_bytes(plate, 0.02))
    assert found["holes"] == []
    side = found["flats"][0]
    assert side["area_mm2"] == pytest.approx(400, rel=1e-6)
    assert [abs(n) for n in side["normal"]] == pytest.approx([0, 1, 0], abs=1e-9)


def test_an_stl_that_is_not_closed_has_no_solid(kernel: Kernel) -> None:
    maker = importlib.import_module("OCP.BRepPrimAPI").BRepPrimAPI_MakeBox(10, 10, 10)
    five_sides = compound(
        maker.TopFace(), maker.FrontFace(), maker.BackFace(), maker.LeftFace(), maker.RightFace()
    )
    assert facts(kernel, MM, stl_bytes(five_sides)) == {
        "kind": "refused",
        "reason": "the file has no solid that can be read: 1 solids or shells, none readable",
    }


@pytest.mark.parametrize(
    ("read_as", "data"),
    [
        pytest.param(
            STEP, step_bytes(compound(box(10, 10, 10), box(4, 4, 4, at=(20, 0, 0)))), id="step"
        ),
        pytest.param(MM, stl_bytes(box(30, 10, 20)), id="stl"),
    ],
)
def test_the_kept_brep_reads_back_and_is_whole_solids(
    kernel: Kernel, read_as: ReadAs, data: bytes
) -> None:
    found = part(kernel, read_as, data)
    shape = kernel.read_brep(base64.b64decode(found["brep"], validate=True))
    assert not isinstance(shape, Unreadable), shape
    assert unmeasurable(kernel, shape) is None
    assert len(kernel.solids(shape)) == found["solids"]
    assert kernel.volume_props(shape).volume == pytest.approx(found["volume_mm3"], rel=1e-12)


def test_a_brep_is_read_as_it_is(kernel: Kernel) -> None:
    plate = cut(box(40, 20, 10), through_hole(6, 20, 10, depth=10))
    found = part(kernel, BREP, brep_bytes(plate))
    assert (found["brep"], found["left_out"], found["names"]) == (None, None, [])
    assert len(found["holes"]) == 1


def test_the_holes_and_flats_are_capped(kernel: Kernel) -> None:
    holes = tuple(through_hole(2, 4 + 6 * (n % 10), 4 + 6 * (n // 10), depth=10) for n in range(80))
    found = part(kernel, BREP, brep_bytes(cut(box(66, 66, 10), *holes)))
    assert len(found["holes"]) == 64
    assert len(found["flats"]) <= 16


def test_the_header_line_picks_how_the_bytes_are_read(kernel: Kernel) -> None:
    found = dict(answer(kernel, b'{"format": "stl", "scale": 25.4}\n' + stl_bytes(box(10, 10, 10))))
    assert found["kind"] == "part", found
    assert found["volume_mm3"] == pytest.approx(1000 * 25.4**3, rel=1e-4)


@pytest.mark.parametrize(
    "stdin",
    [b"", b"no header", b'{"format": "obj", "scale": 1}\nx', b'{"format": "stl", "scale": 0}\nx'],
)
def test_a_missing_or_bad_header_is_refused(kernel: Kernel, stdin: bytes) -> None:
    assert answer(kernel, stdin)["kind"] == "refused"


def test_keeping_solids_counts_the_faces_that_belong_to_no_shell(kernel: Kernel) -> None:
    kept = kernel.keep_solids(compound(box(10, 10, 10), box_face(5, 5, 5)))
    assert (kept.bodies, kept.unreadable, kept.loose) == (1, 0, 1)
    assert kept.solids is not None


def test_keeping_solids_caps_a_loose_tolerance(kernel: Kernel) -> None:
    kept = kernel.keep_solids(loosened(box(10, 10, 10), 0.01))
    assert kept.solids is not None
    assert unmeasurable(kernel, kept.solids) is None


def test_keeping_solids_turns_an_inside_out_solid_back(kernel: Kernel) -> None:
    kept = kernel.keep_solids(compound(inside_out(box(10, 10, 10))))
    assert kept.solids is not None
    assert kernel.volume_props(kept.solids).volume == pytest.approx(1000, rel=1e-9)
    assert kept.unreadable == 0
