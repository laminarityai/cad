import hashlib
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import pytest

from cad.checks.result import CheckRun, StepStored, Verdict
from cad.sandbox.host import run_checks
from cad.sandbox.outcome import Built
from cad.tables.materials import Cited, load_materials
from cad.variants.store import BuildResult, build_variant

PARTS = {
    path.stem: path.read_text()
    for path in (Path(__file__).parents[1] / "sandbox/parts").glob("*.py")
}
PLATE = PARTS["plate"]
GRADE_PY_142404A_VOLUMES_MM3 = {
    "arm": 49489.8584374907,
    "bearing_block": 24736.73203267981,
    "gusset": 3646.63689760239,
    "hex_spacer": 3511.9261474703944,
    "l_bracket": 6684.86152524038,
    "motor_plate": 19126.184280857167,
    "plate": 29509.723050480767,
    "shaft_collar": 3589.161414458382,
    "spur_gear": 17239.394022395285,
    "u_bracket": 9572.743399111692,
}
TOLERANCE_MM3 = 0.01


@pytest.fixture(scope="module")
def built_parts(store: Path) -> Mapping[str, BuildResult]:
    with ThreadPoolExecutor(4) as pool:
        results = pool.map(partial(build_variant, root=store), PARTS.values())
        return dict(zip(PARTS, results, strict=True))


def test_the_grade_volumes_cover_the_reference_parts() -> None:
    assert set(GRADE_PY_142404A_VOLUMES_MM3) == set(PARTS)


@pytest.mark.parametrize("part", sorted(GRADE_PY_142404A_VOLUMES_MM3))
def test_every_check_passes_and_the_volume_matches_grade_py(
    part: str, built_parts: Mapping[str, BuildResult], store: Path
) -> None:
    built = built_parts[part]
    assert built.outcome == Built(), built.output
    run = run_checks(built.variant_id, "prusament-pla", store)
    assert [result.verdict for result in run.results] == [Verdict.PASS] * 3, [
        result.reason for result in run.results
    ]
    for result in run.results:
        assert result.formula
        assert result.sources
    mass = run.result("mass")
    assert abs(mass.number("volume", "mm^3") - GRADE_PY_142404A_VOLUMES_MM3[part]) < TOLERANCE_MM3
    density = load_materials().get_material("prusament-pla").density
    assert isinstance(density, Cited)
    assert mass.sources[-1] == density.source


def test_the_same_variant_checked_twice_serializes_to_the_same_bytes(
    check: Callable[..., CheckRun], store: Path
) -> None:
    first = check(PLATE)
    step = store / first.variant_id / "result.step"
    first_step = step.read_bytes()
    second = check(PLATE)
    assert second.model_dump_json() == first.model_dump_json()
    assert step.read_bytes() == first_step
    assert first.step == StepStored(sha256=hashlib.sha256(first_step).hexdigest())


def table_density(key: str) -> float:
    density = load_materials().get_material(key).density
    assert isinstance(density, Cited)
    return density.magnitude_in("kg/m^3")


def test_mass_ratio_is_the_density_ratio(check: Callable[..., CheckRun]) -> None:
    pla = check(PLATE, "prusament-pla").result("mass")
    aluminium = check(PLATE, "kaiser-6061-t6").result("mass")
    assert pla.number("volume", "mm^3") == aluminium.number("volume", "mm^3")
    ratio = aluminium.number("mass", "kg") / pla.number("mass", "kg")
    expected = table_density("kaiser-6061-t6") / table_density("prusament-pla")
    assert ratio == pytest.approx(expected, rel=1e-4)


@pytest.mark.parametrize("key", ["unobtainium", "prusament-pla ", "PRUSAMENT-PLA"])
def test_a_key_that_is_not_in_the_table_makes_mass_unknown_and_the_other_checks_still_run(
    key: str, check: Callable[..., CheckRun]
) -> None:
    run = check(PLATE, key)
    mass = run.result("mass")
    assert mass.verdict == Verdict.UNKNOWN
    assert repr(key) in mass.reason
    assert mass.number("volume", "mm^3") == pytest.approx(
        GRADE_PY_142404A_VOLUMES_MM3["plate"], abs=0.01
    )
    assert [run.result(id).verdict for id in ("closed_solid", "interference")] == [Verdict.PASS] * 2
    assert isinstance(run.step, StepStored)
