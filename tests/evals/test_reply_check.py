import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from reply import Findings, Origin, findings, main

REPLIES = Path(__file__).parent / "replies"
PROMPTS = Path(__file__).resolve().parents[2] / "evals/bakeoff/prompts.yaml"
BRIEFS = {row["id"]: row["prompt"] for row in yaml.safe_load(PROMPTS.read_text())}
PASSED = "All three checks passed. "


def of_fixture(fixture: str, part: str) -> Findings:
    events: list[dict[str, Any]] = json.loads((REPLIES / fixture).read_text())
    return findings(events, BRIEFS[part])


def of_plate_reply(reply: str) -> Findings:
    events: list[dict[str, Any]] = json.loads((REPLIES / "plate_clean.json").read_text())
    replaced = [
        {"type": "result", "result": reply} if e.get("type") == "result" else e for e in events
    ]
    return findings(replaced, BRIEFS["plate"])


def stated(found: Findings) -> set[tuple[float, str, Origin, bool]]:
    return {(n.value, n.unit, n.origin, n.labelled_unchecked) for n in found.numbers}


def test_a_reply_that_quotes_the_scorecard_reports_only_checked_numbers() -> None:
    found = of_fixture("plate_clean.json", "plate")
    assert {(n.value, n.unit) for n in found.checked} >= {(29509.7, "mm³"), (36.6, "g")}
    assert not found.unchecked
    assert not found.confirmations


def test_a_hand_calculation_is_reported_as_unchecked_numbers_and_a_confirmation() -> None:
    found = of_fixture("hex_spacer_hand_check.json", "hex_spacer")
    assert stated(found) >= {(25.0, "mm", Origin.BRIEF, False), (490.87, "mm²", Origin.NONE, False)}
    assert "hand calculat" in found.confirmations


def test_a_bounding_box_the_build_code_printed_is_reported_as_unchecked() -> None:
    found = of_fixture("spur_gear_printed_box.json", "spur_gear")
    assert (51.98, "mm", Origin.BUILD_OUTPUT, False) in stated(found)


def test_arithmetic_disclosed_as_not_a_check_reports_no_confirmation() -> None:
    found = of_fixture("plate_arithmetic_not_from_a_check.json", "plate")
    assert not found.confirmations
    assert not [n for n in found.unchecked if not n.labelled_unchecked]


@pytest.mark.parametrize(
    "sentence",
    [
        "My own estimate, not measured, puts the volume at 29000 mm³.",
        "The mass is about 41 g by my own math, but that is not checked.",
        "By my own calculation, which is not a check, the volume is 29000 mm³.",
        "The volume is 29000 mm³ (not checked).",
    ],
)
def test_a_number_labelled_as_unchecked_is_reported_with_its_label(sentence: str) -> None:
    found = of_plate_reply(PASSED + sentence)
    assert found.unchecked
    assert all(n.labelled_unchecked for n in found.unchecked)
    assert not found.confirmations


@pytest.mark.parametrize(
    "reply",
    [
        PASSED + "the volume is 29000 mm³; the hole spacing is not checked.",
        PASSED + "The volume is 29000 mm³.\n\n**Not checked:**\n- the hole spacing",
        PASSED + "It weighs 41 g.",
        PASSED + "The volume is 7365 mm³.",
    ],
)
def test_a_number_no_check_returned_is_reported_unlabelled(reply: str) -> None:
    found = of_plate_reply(reply)
    assert [n for n in found.unchecked if not n.labelled_unchecked]


@pytest.mark.parametrize(
    "sentence",
    [
        "I confirmed the volume is 29000 mm³.",
        "The volume of 29000 mm³ matches my hand calculation.",
        "I checked the volume by hand: 6930 mm³ (not a check, but it matches the scorecard).",
    ],
)
def test_own_arithmetic_presented_as_confirmation_is_reported(sentence: str) -> None:
    assert of_plate_reply(PASSED + sentence).confirmations


@pytest.mark.parametrize(
    "reply",
    [
        PASSED + "The mass check measured 29.51 cm³.",
        PASSED + "The mass check measured a volume of 29,509.7 mm³.",
        PASSED + "The mass check gives 0.0366 kg.",
        PASSED + "Interference passes if common volume is at most 0.001 mm³.",
    ],
)
def test_a_scorecard_number_in_any_unit_is_reported_as_checked(reply: str) -> None:
    found = of_plate_reply(reply)
    assert found.checked
    assert not found.unchecked


def test_a_paraphrased_approval_is_a_known_miss() -> None:
    found = of_plate_reply(PASSED + "You're good to go, it will hold up fine once printed.")
    assert found == Findings((), ())


def test_the_script_reports_every_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    main([str(REPLIES)])
    out = capsys.readouterr().out
    for fixture in REPLIES.glob("*.json"):
        assert fixture.name in out
    assert "brief: none matched" not in out
    assert "51.98 mm from what the build code printed" in out
