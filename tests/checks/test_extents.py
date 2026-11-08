from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import pytest

from cad.checks.result import CheckResult, CheckRun, Verdict
from cad.sandbox.host import run_checks
from cad.sandbox.outcome import Built
from cad.variants.store import BuildResult, build_variant

PARTS = {
    path.stem: path.read_text()
    for path in (Path(__file__).parents[1] / "sandbox/parts").glob("*.py")
}
STAR_IMPORT = "from build123d import *\n"
BOX = STAR_IMPORT + "result = Box(10, 20, 30)\n"
CYLINDER = STAR_IMPORT + "result = Cylinder(5, 20)\n"
ROTATED_BOX = STAR_IMPORT + "result = Rot(Z=45) * Box(10, 10, 10)\n"
OFF_ORIGIN_BOX = STAR_IMPORT + "result = Pos(100, -50, 7) * Box(10, 20, 30)\n"
LOOSE_FACE = (
    STAR_IMPORT
    + "result = Compound([Box(10, 10, 10), Pos(30, 0, 0) * Box(10, 10, 10).faces()[0]])\n"
)
OPEN_SHELL = STAR_IMPORT + "result = Shell(Box(10, 10, 10).faces()[:-1])\n"
TWO_BOXES = STAR_IMPORT + "result = Compound([Box(10, 10, 10), Pos(100, 0, 0) * Box(10, 10, 10)])\n"
DIAGONAL = 10 * 2**0.5
SORTED_NAMES = ("smallest", "middle", "largest")
GRADE_PY_142404A_SORTED_EXTENTS_MM = {
    "arm": [6.0, 40.0, 290.0],
    "bearing_block": [20.0, 40.0, 40.0],
    "gusset": [4.0, 45.757, 45.757],
    "hex_spacer": [10.0, 25.0, 25.0],
    "l_bracket": [30.0, 40.0, 40.0],
    "motor_plate": [6.0, 60.0, 60.0],
    "plate": [6.0, 50.0, 100.0],
    "shaft_collar": [10.0, 25.0, 25.0],
    "spur_gear": [10.0, 51.98, 51.98],
    "u_bracket": [30.0, 40.0, 50.0],
}

type Check = Callable[..., CheckRun]


def along_axes(result: CheckResult) -> list[float]:
    return [result.number(f"extent:{axis}", "mm") for axis in "xyz"]


def sorted_extents(result: CheckResult) -> list[float]:
    return [result.number(f"sorted_extent:{name}", "mm") for name in SORTED_NAMES]


def test_a_box_has_its_own_sizes_with_no_tolerance_gap(check: Check) -> None:
    extents = check(BOX).result("extents")
    assert extents.verdict == Verdict.PASS, extents.reason
    assert along_axes(extents) == [10.0, 20.0, 30.0]
    assert sorted_extents(extents) == [10.0, 20.0, 30.0]


def test_a_cylinder_is_as_wide_as_its_diameter_and_as_tall_as_its_height(check: Check) -> None:
    extents = check(CYLINDER).result("extents")
    assert along_axes(extents) == pytest.approx([10.0, 10.0, 20.0], abs=1e-9)
    assert sorted_extents(extents) == pytest.approx([10.0, 10.0, 20.0], abs=1e-9)


def test_a_part_rotated_in_the_plane_is_measured_along_the_axes_not_along_itself(
    check: Check,
) -> None:
    extents = check(ROTATED_BOX).result("extents")
    assert along_axes(extents) == pytest.approx([DIAGONAL, DIAGONAL, 10.0], abs=1e-9)
    assert sorted_extents(extents) == pytest.approx([10.0, DIAGONAL, DIAGONAL], abs=1e-9)


def test_where_the_part_sits_does_not_change_its_extents(check: Check) -> None:
    extents = check(OFF_ORIGIN_BOX).result("extents")
    assert along_axes(extents) == pytest.approx([10.0, 20.0, 30.0], abs=1e-9)


@pytest.mark.parametrize("code", [OPEN_SHELL, LOOSE_FACE, TWO_BOXES], ids=["shell", "face", "two"])
def test_a_shape_that_is_not_one_closed_solid_has_unknown_extents_and_no_number(
    code: str, check: Check
) -> None:
    run = check(code)
    closed, extents = run.result("closed_solid"), run.result("extents")
    assert closed.verdict == Verdict.FAIL
    assert extents.verdict == Verdict.UNKNOWN, extents.reason
    assert extents.measured == ()
    assert closed.reason in extents.reason


def test_the_result_names_its_formula_and_source(check: Check) -> None:
    extents = check(BOX).result("extents")
    assert "bounding box" in extents.formula
    assert [source.page for source in extents.sources] == ["BRepBndLib::AddOptimal"]


@pytest.fixture(scope="module")
def built_parts(store: Path) -> Mapping[str, BuildResult]:
    with ThreadPoolExecutor(4) as pool:
        results = pool.map(partial(build_variant, root=store), PARTS.values())
        return dict(zip(PARTS, results, strict=True))


def test_the_grade_extents_cover_the_reference_parts() -> None:
    assert set(GRADE_PY_142404A_SORTED_EXTENTS_MM) == set(PARTS)


@pytest.mark.parametrize("part", sorted(GRADE_PY_142404A_SORTED_EXTENTS_MM))
def test_the_sorted_extents_of_each_reference_part_match_grade_py(
    part: str, built_parts: Mapping[str, BuildResult], store: Path
) -> None:
    built = built_parts[part]
    assert built.outcome == Built(), built.output
    extents = run_checks(built.variant_id, "prusament-pla", store).result("extents")
    assert extents.verdict == Verdict.PASS, extents.reason
    assert sorted_extents(extents) == pytest.approx(
        GRADE_PY_142404A_SORTED_EXTENTS_MM[part], abs=0.002
    )
