import pytest

from cad.checks.result import BodyMaterial
from cad.scorecard.material import made_of
from cad.variant_sets.model import (
    BodyChoice,
    BodyMaterialsRefused,
    MaterialChoice,
    MaterialMissing,
)
from tests.support.named_bodies import GEAR, ONE_NAMED, PLATE, revision
from tests.support.named_bodies import PLATE_AND_GEARS as TWO

SLOT = revision(
    (
        BodyChoice(body="plate", key=PLATE, reason="carbon fibre is stiff"),
        BodyChoice(body="gear", key=GEAR, reason="steel teeth wear well"),
    )
)


def each(plate: str, gear: str) -> tuple[BodyMaterial, ...]:
    return (BodyMaterial(body="plate", key=plate), BodyMaterial(body="gear", key=gear))


def test_scoring_with_no_materials_reads_what_the_slot_recorded_for_each_body() -> None:
    assert made_of(TWO, None, {}, {}, SLOT) == each(PLATE, GEAR)


def test_an_entry_replaces_one_body_and_the_others_keep_the_slot_s_choice() -> None:
    assert made_of(TWO, None, {"gear": PLATE}, {}, SLOT) == each(PLATE, PLATE)


def test_the_person_s_made_of_covers_every_body_with_no_slot_choice() -> None:
    assert made_of(TWO, None, {}, {None: GEAR}, None) == each(GEAR, GEAR)


def test_a_body_nothing_names_is_refused_by_name() -> None:
    with pytest.raises(MaterialMissing, match="for the bodies gear"):
        made_of(TWO, None, {"plate": PLATE}, {}, None)


def test_one_key_scores_one_named_body_but_not_two() -> None:
    assert made_of(ONE_NAMED, PLATE, {}, {}, None) == (BodyMaterial(body="plate", key=PLATE),)
    with pytest.raises(BodyMaterialsRefused, match="the bodies plate, gear"):
        made_of(TWO, PLATE, {}, {}, SLOT)


def test_an_entry_for_a_body_the_variant_does_not_hold_is_refused() -> None:
    with pytest.raises(BodyMaterialsRefused, match="materials names spacer"):
        made_of(TWO, None, {"spacer": GEAR}, {}, SLOT)


def test_one_unnamed_body_scores_with_one_key_and_refuses_materials() -> None:
    chose = revision(material=MaterialChoice(key=PLATE, reason="it is light"))
    assert made_of((), None, {}, {}, chose) == PLATE
    with pytest.raises(BodyMaterialsRefused, match="one unnamed body"):
        made_of((), None, {"plate": PLATE}, {}, chose)
