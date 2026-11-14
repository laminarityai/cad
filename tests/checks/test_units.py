import time

import pytest

from tests.support.rows import TEXT
from tests.support.session import Session

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("magnitude", "unit", "says"),
    [
        (150, "10**10**10", "not a unit"),
        (150, "g*" * 4500 + "g", "not a unit"),
        (10**309, "g", "too large"),
    ],
    ids=["arithmetic", "long", "huge"],
)
async def test_a_mass_the_agent_cannot_state_is_refused_at_once(
    s: Session, magnitude: int, unit: str, says: str
) -> None:
    brief_id = (await s.call("create_brief", text=TEXT))["brief_id"]
    mass = {"magnitude": magnitude, "unit": unit}
    started = time.monotonic()
    result = await s.client.call_tool(
        "propose_requirements",
        {
            "brief_id": brief_id,
            "requirements": [
                {"target": {"kind": "max_mass", "mass": mass}, "quote": "under 150 g"}
            ],
        },
    )
    assert time.monotonic() - started < 2
    assert result.is_error
    assert says in result.content[0].model_dump()["text"]
