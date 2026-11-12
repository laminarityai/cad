from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cad.agent_checks import harness
from tests.support.holed_plate import confirmed, own

if TYPE_CHECKING:
    from tests.support.browser import Person
    from tests.support.session import Session

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("raise ValueError('agent bug')", "ValueError('agent bug')"),
        ("report('x', float('nan'), 'mm')", "not a finite number"),
        ("report('x', 1.0, 'inch')", "has unit 'inch'"),
        ("report('Bad Name', 1.0, 'mm')", "does not match"),
        ("report('x', 1.0, 'mm'); report('x', 2.0, 'mm')", "reported twice"),
        ("report('a', 1.0, 'mm'); print('x' * 9000); report('b', 1.0, 'mm')", "last 8 KiB"),
    ],
)
@pytest.mark.docker
async def test_a_broken_measurement_fails_with_its_reason_and_no_value(
    s: Session, person: Person, code: str, reason: str
) -> None:
    assert reason in await failed_measurement(s, person, code)


@pytest.mark.docker
async def test_a_measurement_that_never_ends_is_stopped_at_the_wall_limit(
    s: Session, person: Person, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(harness, "WALL_SECONDS", 5)
    assert "timed out after 5 s" in await failed_measurement(s, person, "while True:\n    pass")


async def failed_measurement(s: Session, person: Person, code: str) -> str:
    brief_id, r2, variant_id = await confirmed(s, person)
    card = await s.call(
        "score_variant",
        variant_id=variant_id,
        material_key="prusament-pla",
        brief_id=brief_id,
        own_measurements=[own(r2, code)],
    )
    [row] = card["not_verified"]
    assert row["values"] == []
    return str(row["failed"])
