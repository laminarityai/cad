import pytest

from cad.scorecard.material import MaterialPinned
from cad.tables.materials import load_materials
from cad.variant_sets.model import (
    BodyChoice,
    BodyMaterialsRefused,
    Chosen,
    MaterialMissing,
)
from cad.variant_sets.placement import choose_each
from tests.support.named_bodies import GEAR, ONE_NAMED, PLATE, revision
from tests.support.named_bodies import PLATE_AND_GEARS as TWO

TABLE = load_materials()
NONE = (None, None)


def chose(body: str, key: str) -> BodyChoice:
    return BodyChoice(body=body, key=key, reason=f"{key} suits the {body}")


def test_each_named_body_records_the_material_asked_for_it_in_body_order() -> None:
    asked = [chose("gear", GEAR), chose("plate", PLATE)]
    chosen = choose_each(None, None, TWO, NONE, asked, TABLE)
    assert chosen == Chosen(materials=(chose("plate", PLATE), chose("gear", GEAR)))


def test_a_body_left_out_keeps_the_choice_the_slot_made_for_that_name() -> None:
    before = revision((chose("plate", PLATE), chose("gear", GEAR)))
    chosen = choose_each(None, before, TWO, NONE, [chose("gear", PLATE)], TABLE)
    assert chosen.materials == (chose("plate", PLATE), chose("gear", PLATE))


def test_a_body_no_entry_or_earlier_revision_names_is_refused_by_name() -> None:
    with pytest.raises(MaterialMissing, match="for the bodies gear"):
        choose_each(None, None, TWO, NONE, [chose("plate", PLATE)], TABLE)


def test_an_entry_for_a_body_the_code_did_not_build_is_refused() -> None:
    asked = [chose("plate", PLATE), chose("gear", GEAR), chose("spacer", GEAR)]
    with pytest.raises(BodyMaterialsRefused, match="materials names spacer"):
        choose_each(None, None, TWO, NONE, asked, TABLE)


def test_one_material_key_on_a_variant_of_two_bodies_is_refused() -> None:
    with pytest.raises(BodyMaterialsRefused, match="the bodies plate, gear"):
        choose_each(None, None, TWO, (PLATE, "it is light"), [], TABLE)


def test_one_material_key_on_a_variant_of_one_named_body_names_that_body() -> None:
    chosen = choose_each(None, None, ONE_NAMED, (PLATE, "it is light"), [], TABLE)
    assert chosen.materials == (BodyChoice(body="plate", key=PLATE, reason="it is light"),)


def test_materials_and_a_material_key_together_are_refused() -> None:
    with pytest.raises(BodyMaterialsRefused, match="not both"):
        choose_each(None, None, TWO, (PLATE, "light"), [chose("plate", PLATE)], TABLE)


def test_materials_on_one_unnamed_body_are_refused() -> None:
    with pytest.raises(BodyMaterialsRefused, match="one unnamed body"):
        choose_each(None, None, (), NONE, [chose("plate", PLATE)], TABLE)


def test_the_person_s_made_of_pins_every_body_and_refuses_an_entry_that_differs() -> None:
    assert choose_each(PLATE, None, TWO, NONE, [chose("gear", PLATE)], TABLE) == Chosen()
    with pytest.raises(MaterialPinned, match="pins every body"):
        choose_each(PLATE, None, TWO, NONE, [chose("gear", GEAR)], TABLE)
