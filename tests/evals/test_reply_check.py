import json
from pathlib import Path
from typing import Any

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
