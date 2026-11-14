from collections.abc import Callable
from pathlib import Path

import pytest

from cad.checks.result import BodyMaterial, CheckResult, Verdict
from cad.scorecard import score
from cad.scorecard.model import JOINTS, Scorecard
from cad.tables.materials import Known, load_materials
from tests.support.named_bodies import GEAR, PLATE

pytestmark = pytest.mark.docker

TABLE = load_materials()
GEARS_ON_A_PLATE = """
from build123d import *
plate = Box(80, 40, 4)
plate.label = "plate"
teeth = [Pos(x, 0, 6) * Cylinder(8, 6) for x in (-20, 20)]
result = Compound(children=[plate, Compound(children=teeth, label="gear")])
"""
STACKED_HOLES = """
from build123d import *
top = Box(40, 40, 5) - Cylinder(3, 5)
top.label = "top"
bottom = Pos(0, 0, -50) * (Box(40, 40, 5) - Cylinder(3, 5))
bottom.label = "bottom"
result = Compound(children=[top, bottom])
"""


def density(key: str) -> float:
    found = TABLE.get_material(key).density
    assert isinstance(found, Known)
    return found.magnitude_in("kg/mm^3")


def scored(
    code: str, made: tuple[BodyMaterial, ...], built: Callable[[str], str], store: Path
) -> Scorecard:
    return score.score_variant(built(code), made, store)


def result(card: Scorecard, check_id: str) -> CheckResult:
    return next(one for one in card.finished if one.check_id == check_id)


def test_a_variant_of_two_materials_weighs_each_body_at_its_own_row(
    built: Callable[[str], str], store: Path
) -> None:
    made = (BodyMaterial(body="plate", key=PLATE), BodyMaterial(body="gear", key=GEAR))
    card = scored(GEARS_ON_A_PLATE, made, built, store)
    mass = result(card, "mass")
    assert mass.verdict == Verdict.PASS
    each = {body: mass.number(f"volume:{body}", "mm^3") for body in ("plate", "gear")}
    expected = each["plate"] * density(PLATE) + each["gear"] * density(GEAR)
    assert mass.number("mass", "kg") == pytest.approx(expected)
    assert [one.body for one in card.materials] == ["plate", "gear"]
    assert card.untested == (JOINTS,)


def test_coaxial_holes_of_two_bodies_read_as_one_hole_of_the_whole_result(
    built: Callable[[str], str], store: Path
) -> None:
    made = (BodyMaterial(body="top", key=PLATE), BodyMaterial(body="bottom", key=PLATE))
    holes = result(scored(STACKED_HOLES, made, built, store), "holes")
    assert holes.number("hole_count", "dimensionless") == 1
    assert holes.number("hole_diameter:0", "mm") == pytest.approx(6.0)
