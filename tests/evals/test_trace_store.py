from dataclasses import replace
from pathlib import Path

import pytest
from cards import (
    genuine_card,
    lines,
    put,
    trace,
    with_result,
)
from provenance import (
    CardTrace,
    Incomplete,
)
from trace_store import SPEC_BY_ID, Tally, exit_code, main, tally
from tracking import NO_REQUIREMENTS, NoRequirements, describe, outcomes_of, track


def test_the_command_passes_on_a_store_of_genuine_scorecards(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(store, genuine_card())
    assert main(["--root", str(store)]) == 0
    out = lines(capsys)
    assert "cards unreadable: 0, unbound: 0, incomplete: 0" in out
    count = len(trace(genuine_card(), store).numbers)
    assert f"numbers resolved: {count}, stale: 0, unresolved: 0" in out
    assert "strict pass rate: no requirements" in out


def test_the_command_prints_the_chain_of_a_computed_number(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(store, genuine_card())
    assert main(["--root", str(store), "--steps"]) == 0
    out = lines(capsys)
    assert "mass.volume = " in out
    assert f"computed by check mass at version {SPEC_BY_ID['mass'].version[:12]}" in out
    assert "table prusament-pla.density" in out


def test_the_command_counts_each_kind_of_failure_on_its_own(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(store, with_result(genuine_card(brep_sha256="f" * 64, results=()), "mass"))
    assert main(["--root", str(store)]) == 1
    out = lines(capsys)
    assert "cards unreadable: 0, unbound: 1, incomplete: 1" in out


def test_the_command_fails_on_an_unreadable_scorecard(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(store, '{"variant_id": "0123456789abcdef"}')
    assert main(["--root", str(store)]) == 1
    out = lines(capsys)
    assert "UNREADABLE" in out
    assert "cards unreadable: 1, unbound: 0, incomplete: 0" in out


def test_the_command_fails_on_a_card_stored_under_another_variant_id(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(store, genuine_card(variant_id="fedcba9876543210"))
    assert main(["--root", str(store)]) == 1
    assert "stored under" in lines(capsys)


def test_the_command_fails_on_a_store_with_no_scorecard(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path)]) == 1


def test_stale_and_unresolved_numbers_are_counted_apart(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    card = with_result(genuine_card(), "extents", version="0" * 64)
    put(store, card.model_copy(update={"material_key": "unobtainium"}))
    assert main(["--root", str(store)]) == 1
    out = lines(capsys)
    assert "stale: 2, unresolved: 1" in out


COUNTS = Tally(
    cards=1, unreadable=0, unbound=0, incomplete=0, numbers=3, resolved=3, stale=0, unresolved=0
)


@pytest.mark.parametrize(
    ("counts", "code"),
    [
        (COUNTS, 0),
        (replace(COUNTS, cards=0), 1),
        (replace(COUNTS, numbers=0, resolved=0), 1),
        (replace(COUNTS, unreadable=1), 1),
        (replace(COUNTS, unbound=1), 1),
        (replace(COUNTS, incomplete=1), 1),
        (replace(COUNTS, stale=1, resolved=2), 1),
        (replace(COUNTS, unresolved=1, resolved=2), 1),
    ],
)
def test_one_function_decides_the_exit_code(counts: Tally, code: int) -> None:
    assert exit_code(counts) == code


def test_the_tally_counts_a_card_once_per_kind_of_failure() -> None:
    traced = CardTrace("a" * 16, (Incomplete("x"), Incomplete("y")), ())
    assert tally([traced]).incomplete == 1


def test_scorecards_without_requirements_report_no_requirements_and_do_not_divide() -> None:
    tracking = track(outcomes_of(genuine_card()))
    assert tracking.strict_pass_rate == NoRequirements()
    assert tracking.reviewed_coverage == NoRequirements()
    assert describe(tracking.strict_pass_rate) == NO_REQUIREMENTS
