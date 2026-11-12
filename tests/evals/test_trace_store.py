import json
from dataclasses import replace
from pathlib import Path

import pytest
from provenance import (
    CardTrace,
    Incomplete,
)
from trace_store import SPEC_BY_ID, Tally, exit_code, main, tally
from tracking import NO_REQUIREMENTS, NoRequirements, describe, outcomes_of, track

from cad.briefs import store as briefs
from cad.checks.result import Measure
from cad.projects.model import new_project_id
from cad.sandbox.outcome import Build, Built
from cad.scorecard.model import AwaitingConfirmation, Scorecard
from cad.variants import entry
from tests.support.cards import (
    BREP,
    BRIEF_TEXT,
    STEP,
    UNITS,
    VARIANT_ID,
    confirm_on_page,
    drafts,
    genuine_card,
    judged_card,
    lines,
    result_of,
    roots_beside,
    trace,
    transcript_of,
    with_result,
    write_transcript,
)

LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}, "under 150 g")
FRIENDLY = ({"kind": "unchecked", "statement": "looks friendly"}, "looks friendly")


def bare(store: Path) -> list[str]:
    return [str(transcript_of(store)), "--root", str(store)]


def arguments_for(store: Path) -> list[str]:
    roots = roots_beside(store)
    return [
        str(transcript_of(store)),
        "--root",
        str(store),
        "--briefs-root",
        str(roots.briefs),
        "--projects-root",
        str(roots.projects),
    ]


def judged_against_a_brief(store: Path) -> Scorecard:
    roots = roots_beside(store)
    brief_id = briefs.create_brief(roots, BRIEF_TEXT, new_project_id()).id
    return judged_card(confirm_on_page(roots, brief_id, drafts(LIGHT, FRIENDLY)))


def scored_against_a_brief(store: Path) -> list[str]:
    write_transcript(store, judged_against_a_brief(store))
    return arguments_for(store)


def test_the_command_passes_on_a_store_of_genuine_scorecards(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_transcript(store, genuine_card())
    assert main(bare(store)) == 0
    out = lines(capsys)
    assert "cards unreadable: 0, unbound: 0, incomplete: 0" in out
    count = len(trace(genuine_card(), store).numbers)
    assert f"numbers resolved: {count}, stale: 0, unresolved: 0" in out
    assert "strict pass rate: no requirements" in out


def test_the_command_prints_the_chain_of_a_computed_number(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_transcript(store, genuine_card())
    assert main([*bare(store), "--steps"]) == 0
    out = lines(capsys)
    assert "mass.volume = " in out
    assert f"computed by check mass at version {SPEC_BY_ID['mass'].version[:12]}" in out
    assert "table prusament-pla.density" in out


def test_the_command_counts_each_kind_of_failure_on_its_own(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_transcript(store, with_result(genuine_card(brep_sha256="f" * 64, results=()), "mass"))
    assert main(bare(store)) == 1
    out = lines(capsys)
    assert "cards unreadable: 0, unbound: 1, incomplete: 1" in out


def test_the_command_fails_on_an_unreadable_scorecard(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_transcript(store, '{"variant_id": "0123456789abcdef"}')
    assert main(bare(store)) == 1
    out = lines(capsys)
    assert "UNREADABLE" in out
    assert "cards unreadable: 1, unbound: 0, incomplete: 0" in out


def test_the_command_fails_on_a_card_for_a_variant_the_store_never_built(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_transcript(store, genuine_card(variant_id="fedcba9876543210"))
    assert main(bare(store)) == 1
    assert "cards unreadable: 0, unbound: 1" in lines(capsys)


def test_the_command_fails_on_a_store_with_no_scorecard(tmp_path: Path) -> None:
    assert main([str(tmp_path / "transcript.json"), "--root", str(tmp_path)]) == 1


def test_stale_and_unresolved_numbers_are_counted_apart(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    card = with_result(genuine_card(), "extents", version="0" * 64)
    write_transcript(store, card.model_copy(update={"material_key": "unobtainium"}))
    assert main(bare(store)) == 1
    out = lines(capsys)
    assert "stale: 2, unresolved: 1" in out


def test_a_card_judged_against_a_confirmed_brief_resolves_and_reports_its_requirements(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = scored_against_a_brief(store)
    assert main([*arguments, "--steps", "--require-judged"]) == 0
    out = lines(capsys)
    assert "cards unconfirmed: 0, misjudged: 0, superseded: 0" in out
    assert "cards judged: 1, awaiting confirmation: 0, no brief: 0" in out
    assert "confirmed by a person: brief " in out
    assert "strict pass rate: 0/2 (0%)" in out
    assert "requirements covered by reviewed checks: 1/2 (50%)" in out


def test_awaiting_and_no_brief_cards_count_apart_and_fail_only_when_judgment_is_required(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    brief_id = briefs.create_brief(roots_beside(store), BRIEF_TEXT, new_project_id()).id
    write_transcript(store, genuine_card(basis=AwaitingConfirmation(brief_id=brief_id)))
    arguments = arguments_for(store)
    assert main(arguments) == 0
    assert "cards judged: 0, awaiting confirmation: 1, no brief: 0" in lines(capsys)
    assert main([*arguments, "--require-judged"]) == 1
    write_transcript(store, genuine_card())
    assert main([*arguments, "--require-judged"]) == 1
    assert "cards judged: 0, awaiting confirmation: 0, no brief: 1" in lines(capsys)


OTHER_VARIANT = "fedcba9876543210"


def test_a_card_whose_deciding_measure_has_the_wrong_dimension_is_misjudged_and_the_run_goes_on(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = judged_against_a_brief(store)
    wrong = tuple(
        Measure(name=one.name, value=UNITS.Quantity(1.0, "mm")) if one.name == "mass" else one
        for one in result_of(good, "mass").measured
    )
    other = good.model_copy(update={"variant_id": OTHER_VARIANT})
    entry.save(
        store, entry.VariantId(OTHER_VARIANT), "x = 1\n", Build(outcome=Built(), output=""), BREP
    )
    (store / OTHER_VARIANT / entry.STEP).write_bytes(STEP)
    write_transcript(store, with_result(good, "mass", measured=wrong), other)
    assert main(arguments_for(store)) == 1
    out = lines(capsys)
    assert f"FAIL {VARIANT_ID}" in out
    assert "MISJUDGED" in out
    assert f"ok   {OTHER_VARIANT}" in out
    assert "cards unconfirmed: 0, misjudged: 1, superseded: 0" in out


@pytest.mark.parametrize("unit", ["nonsense_unit", "g/0"])
@pytest.mark.parametrize("where", ["measure", "limit"])
def test_a_card_with_an_unparseable_unit_is_unreadable_and_the_run_goes_on(
    store: Path, capsys: pytest.CaptureFixture[str], where: str, unit: str
) -> None:
    good = judged_against_a_brief(store)
    data = json.loads(good.model_dump_json())
    if where == "measure":
        mass = next(one for one in data["results"] if one["check_id"] == "mass")
        next(one for one in mass["measured"] if one["name"] == "mass")["value"]["unit"] = unit
    else:
        data["basis"]["requirements"][0]["comparisons"][0]["limit"]["unit"] = unit
    other = good.model_copy(update={"variant_id": OTHER_VARIANT})
    entry.save(
        store, entry.VariantId(OTHER_VARIANT), "x = 1\n", Build(outcome=Built(), output=""), BREP
    )
    (store / OTHER_VARIANT / entry.STEP).write_bytes(STEP)
    write_transcript(store, json.dumps(data), other)
    assert main(arguments_for(store)) == 1
    out = lines(capsys)
    assert "FAIL card 1" in out
    assert "UNREADABLE" in out
    assert f"ok   {OTHER_VARIANT}" in out
    assert "cards unreadable: 1" in out


COUNTS = Tally(
    cards=1,
    unreadable=0,
    unbound=0,
    unlinked=0,
    incomplete=0,
    unconfirmed=0,
    misjudged=0,
    superseded=0,
    unfitted=0,
    judged=1,
    awaiting=0,
    no_brief=0,
    numbers=3,
    resolved=3,
    stale=0,
    unresolved=0,
    not_verified=0,
    agent_checked=0,
)


@pytest.mark.parametrize(
    ("counts", "code"),
    [
        (COUNTS, 0),
        (replace(COUNTS, numbers=4, not_verified=1), 0),
        (replace(COUNTS, numbers=4, agent_checked=1), 0),
        (replace(COUNTS, cards=0), 1),
        (replace(COUNTS, numbers=0, resolved=0), 1),
        (replace(COUNTS, unreadable=1), 1),
        (replace(COUNTS, unbound=1), 1),
        (replace(COUNTS, unlinked=1), 1),
        (replace(COUNTS, incomplete=1), 1),
        (replace(COUNTS, unfitted=1), 1),
        (replace(COUNTS, stale=1, resolved=2), 1),
        (replace(COUNTS, unresolved=1, resolved=2), 1),
        (replace(COUNTS, unconfirmed=1), 1),
        (replace(COUNTS, misjudged=1), 1),
        (replace(COUNTS, superseded=1), 1),
        (replace(COUNTS, judged=0, awaiting=1), 0),
        (replace(COUNTS, judged=0, no_brief=1), 0),
    ],
)
def test_one_function_decides_the_exit_code(counts: Tally, code: int) -> None:
    assert exit_code(counts) == code


@pytest.mark.parametrize(
    ("counts", "code"),
    [
        (COUNTS, 0),
        (replace(COUNTS, judged=0, awaiting=1), 1),
        (replace(COUNTS, judged=0, no_brief=1), 1),
    ],
)
def test_requiring_judgment_fails_a_card_that_judged_no_requirement(
    counts: Tally, code: int
) -> None:
    assert exit_code(counts, require_judged=True) == code


def test_the_tally_counts_a_card_once_per_kind_of_failure() -> None:
    traced = CardTrace("a" * 16, (Incomplete("x"), Incomplete("y")), ())
    assert tally([traced]).incomplete == 1


def test_scorecards_without_requirements_report_no_requirements_and_do_not_divide() -> None:
    tracking = track(outcomes_of(genuine_card()))
    assert tracking.strict_pass_rate == NoRequirements()
    assert tracking.reviewed_coverage == NoRequirements()
    assert describe(tracking.strict_pass_rate) == NO_REQUIREMENTS
