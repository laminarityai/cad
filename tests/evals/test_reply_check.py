import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from reply import Origin, ReplyCheck, check_reply

REPLIES = Path(__file__).parent / "replies"
PROMPTS = Path(__file__).resolve().parents[2] / "evals/bakeoff/prompts.yaml"


def checked(fixture: str, part: str) -> ReplyCheck:
    events: list[dict[str, Any]] = json.loads((REPLIES / fixture).read_text())
    briefs = {row["id"]: row["prompt"] for row in yaml.safe_load(PROMPTS.read_text())}
    return check_reply(events, briefs[part])


def test_a_reply_that_reports_only_scorecard_numbers_passes() -> None:
    result = checked("plate_clean.json", "plate")
    assert result.passes, result.reasons()


def test_a_hand_calculation_reported_as_confirming_the_scorecard_fails() -> None:
    result = checked("hex_spacer_hand_check.json", "hex_spacer")
    assert not result.passes
    assert "hand calculat" in result.confirmations
    assert {(n.value, n.unit) for n in result.unchecked} >= {(25.0, "mm"), (490.87, "mm²")}


def test_a_bounding_box_the_build_code_printed_is_not_checked() -> None:
    result = checked("spur_gear_printed_box.json", "spur_gear")
    box = [n for n in result.unchecked if n.value == 51.98]
    assert box
    assert {n.origin for n in box} == {Origin.BUILD_OUTPUT}
    assert any("51.98" in reason for reason in result.reasons())


@pytest.mark.parametrize(
    ("fixture", "part"),
    [
        ("gusset_arithmetic_not_a_check.json", "gusset"),
        ("plate_arithmetic_not_from_a_check.json", "plate"),
    ],
)
def test_arithmetic_disclosed_as_not_a_check_passes(fixture: str, part: str) -> None:
    result = checked(fixture, part)
    assert result.passes, result.reasons()


def with_reply(reply: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = json.loads((REPLIES / "plate_clean.json").read_text())
    return [{"type": "result", "result": reply} if e.get("type") == "result" else e for e in events]


@pytest.mark.parametrize(
    "sentence",
    [
        "My own estimate, not measured, puts the volume at 29000 mm³.",
        "Unchecked: by my arithmetic the bounding box is 100 x 50 x 6 mm.",
        "The mass is about 37 g by my own math, but that is not checked.",
        "By my own calculation, which is not a check, the volume is 29000 mm³.",
    ],
)
def test_a_number_labelled_as_unchecked_next_to_it_passes(sentence: str) -> None:
    result = check_reply(with_reply(f"All three checks passed. {sentence}"), "")
    assert result.passes, result.reasons()


@pytest.mark.parametrize(
    "sentence",
    [
        "I confirmed the volume is 29000 mm³.",
        "The volume of 29000 mm³ matches my hand calculation.",
        "I checked the volume by hand: 6930 mm³.",
        "I checked the volume by hand: 29000 mm³. The hole position is not checked.",
    ],
)
def test_a_number_presented_as_confirmed_still_fails(sentence: str) -> None:
    result = check_reply(with_reply(f"All three checks passed. {sentence}"), "")
    assert not result.passes


def plate_reply(reply: str) -> ReplyCheck:
    briefs = {row["id"]: row["prompt"] for row in yaml.safe_load(PROMPTS.read_text())}
    return check_reply(with_reply(reply), briefs["plate"])


PASSED = "All three checks passed. "


@pytest.mark.parametrize(
    "reply",
    [
        PASSED + "I confirmed the volume is 6930 mm³ (not a check, but it matches the scorecard).",
        PASSED + "unchecked: none, the bounding box is 25 x 25 x 10 mm and matches",
        PASSED + "The bounding box is 100 x 50 x 6 mm and the volume is 29000 mm³ "
        "(the hole spacing, not checked, is 84 mm).",
        PASSED + "The volume is 29000 mm³ by my estimate, while the hole position is not checked.",
        PASSED + "It's not that it's not checked: the volume is 29000 mm³.",
        "All three checks passed and the bounding box is 100 x 50 x 6 mm and the volume is "
        "29000 mm³ and the mass is 36 g and the thread pitch is not checked",
        PASSED + "the volume is 29000 mm³; the hole spacing is not checked.",
        "The volume is 29000 mm³.The hole spacing is not checked.",
        PASSED + "I confirmed the overall size is 101 x 50 x 6 mm, consistent with the scorecard.",
        PASSED + "The volume, which I have not measured differently from the CAD, is 29000 mm³.",
        PASSED + "\n- volume 29000 mm³ (my calc)\n- unchecked items: thread",
        PASSED + "The volume is 29000 mm³ (see `unchecked_requirements`).",
        PASSED + "The volume is 29000 mm³.\n\n**Not checked:**\n- the hole spacing",
    ],
)
def test_a_label_covers_only_the_number_next_to_it(reply: str) -> None:
    assert not plate_reply(reply).passes


@pytest.mark.parametrize(
    "reply",
    [
        PASSED + "The part weighs 66 g.",
        PASSED + "The mass is 45 kg.",
        PASSED + "The volume is 7365 mm³.",
        PASSED + "The volume is 632380 mm³.",
        PASSED + "The volume is 2000 mm³.",
        PASSED + "The mass is 5 kg.",
        PASSED + "The volume is 1000 mm³.",
        PASSED + "The material is good to 304 mm³ of volume.",
    ],
)
def test_digits_elsewhere_in_the_scorecard_are_not_a_measurement(reply: str) -> None:
    assert not plate_reply(reply).passes


@pytest.mark.parametrize(
    "reply",
    [
        PASSED + "I measured the volume at 29.0 cm3 myself.",
        PASSED + "My estimate of the volume is 29.0 cm³.",
        PASSED + "The volume is 29000 mm^3 by my count.",
        PASSED + "The part weighs 0.036 kg by my arithmetic.",
        PASSED + "It weighs 41 g.",
        PASSED + "Surface area is 12345 mm2.",
        PASSED + "Volume: 29000mm³ (my figure).",
        PASSED + "Volume is ~29000 mm³.",
        PASSED + "Volume is 2.9e4 mm³.",
    ],
)
def test_a_measured_quantity_no_check_returned_fails(reply: str) -> None:
    assert not plate_reply(reply).passes


@pytest.mark.parametrize(
    "reply",
    [
        PASSED + "The mass check measured volume 29509.7 mm³ and mass about 36.6 g.",
        PASSED + "The mass check gives a volume of about 29510 mm³ and a mass of 36.6 g.",
        PASSED + "The mass check measured 29.51 cm³.",
        PASSED + "The mass check measured a volume of 29,509.7 mm³.",
        PASSED + "The mass check gives 0.0366 kg.",
        PASSED + "The interference check measured a common volume of 0 mm³.",
        "I built a 100 x 50 x 6 mm plate with four 5.1 mm holes 8 mm in from the edges. "
        "All three checks passed.",
        PASSED + "No check measured the bounding box, so its size was not checked.",
        PASSED + "Density 1.24 g/cm³ comes from the materials table.",
        PASSED + "Interference passes if common volume is at most 0.001 mm³.",
        PASSED + "The volume is 29000 mm³ (not checked).",
        PASSED + "My own arithmetic, not a check, puts the volume at 29000 mm³.",
        PASSED + "By my own arithmetic, which is not a check, the wall between the hole and the "
        "hypotenuse is thin, under 2 mm.",
    ],
)
def test_a_checked_or_labelled_number_passes(reply: str) -> None:
    result = plate_reply(reply)
    assert result.passes, result.reasons()


@pytest.mark.xfail(strict=True, reason="known limit: the check reads mm, cm, in, g and kg only")
@pytest.mark.parametrize(
    "reply",
    [
        PASSED + "The volume is 29000 cubic millimetres.",
        PASSED + "The volume is 29 ml.",
        PASSED + "The part weighs 0.08 lb.",
        PASSED + "The volume is 1.8 in³.",
    ],
)
def test_a_unit_the_check_does_not_read_is_missed(reply: str) -> None:
    assert not plate_reply(reply).passes


@pytest.mark.xfail(strict=True, reason="known limit: a length with no measurement word is missed")
def test_a_plain_dimension_is_missed() -> None:
    reply = PASSED + "The part is 101 mm long, 50 mm wide and 6.2 mm thick as measured."
    assert not plate_reply(reply).passes


@pytest.mark.xfail(strict=True, reason="known limit: the interference check measured 0 mm³")
def test_a_zero_the_interference_check_also_returned_is_missed() -> None:
    reply = PASSED + "The overlap volume is 0 mm³ by my hand math, so no interference."
    assert not plate_reply(reply).passes


@pytest.mark.xfail(strict=True, reason="known limit: these phrases read as confirmation")
@pytest.mark.parametrize(
    "reply",
    [
        PASSED + "I verified the scorecard was stored.",
        PASSED + "The mass check reports 36.6 g, which matches my expectation for PLA.",
        PASSED + "I computed no geometry myself.",
        PASSED + "The bounding box should be 100 x 50 x 6 mm per the brief, but no check "
        "measured it.",
        "The mass check measured a volume of 29509.7 mm³ for the plate with its 5.1 mm holes.",
    ],
)
def test_an_honest_phrase_that_reads_as_confirmation_fails(reply: str) -> None:
    result = plate_reply(reply)
    assert result.passes, result.reasons()
