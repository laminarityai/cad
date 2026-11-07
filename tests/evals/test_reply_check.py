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
def test_a_number_labelled_as_unchecked_in_its_sentence_passes(sentence: str) -> None:
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
