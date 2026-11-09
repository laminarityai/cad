from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cad.accounts.meter import AccountMeter
from cad.sandbox.meter import AccountLimitReached

NOON = datetime(2026, 11, 9, 12, tzinfo=UTC)


def at(moment: datetime, usage: Path, cap: int | None = 100) -> AccountMeter:
    return AccountMeter(usage, cap, now=lambda: moment)


def test_settled_seconds_replace_the_reserved_ceiling(tmp_path: Path) -> None:
    meter = at(NOON, tmp_path)
    meter.settle(meter.reserve("build", 75), 5.4)
    meter.settle(meter.reserve("check", 75), 90)
    meter.reserve("build", 75)
    with pytest.raises(AccountLimitReached, match="170 of 100 container-seconds"):
        meter.reserve("build", 75)


def test_an_unsettled_reservation_counts_at_its_ceiling(tmp_path: Path) -> None:
    meter = at(NOON, tmp_path)
    meter.reserve("build", 100)
    with pytest.raises(AccountLimitReached, match="100 of 100 container-seconds"):
        meter.reserve("build", 1)


def test_a_refusal_names_when_the_cap_resets(tmp_path: Path) -> None:
    meter = at(NOON, tmp_path, cap=0)
    with pytest.raises(AccountLimitReached, match="resets at 2026-11-10 00:00 UTC"):
        meter.reserve("check", 1)


def test_the_cap_is_per_utc_day(tmp_path: Path) -> None:
    at(NOON, tmp_path).reserve("build", 100)
    tomorrow = at(NOON + timedelta(days=1), tmp_path)
    tomorrow.settle(tomorrow.reserve("build", 75), 1)


def test_a_container_that_runs_past_midnight_settles_on_the_day_it_started(
    tmp_path: Path,
) -> None:
    reservation = at(NOON, tmp_path).reserve("build", 100)
    at(NOON + timedelta(days=1), tmp_path).settle(reservation, 1)
    at(NOON, tmp_path).reserve("build", 1)


def test_no_cap_records_use_and_never_refuses(tmp_path: Path) -> None:
    meter = at(NOON, tmp_path, cap=None)
    for _ in range(3):
        meter.reserve("build", 10_000)
    assert len((tmp_path / "2026-11-09.jsonl").read_text().splitlines()) == 3


def test_a_torn_last_line_is_skipped(tmp_path: Path) -> None:
    meter = at(NOON, tmp_path)
    meter.reserve("build", 50)
    with (tmp_path / "2026-11-09.jsonl").open("a") as file:
        file.write('{"op": "reserve", "id": "x", "sec')
    meter.reserve("build", 1)
    with pytest.raises(AccountLimitReached, match="51 of 51"):
        at(NOON, tmp_path, cap=51).reserve("build", 1)
