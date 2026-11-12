"""A plate under a load, for the tests that wait for a real stress solve.

One solve takes about 100 seconds in CI, and a test file runs on one worker. So each of those
tests has its own file, and the shards and workers can run the solves side by side.
"""

from pathlib import Path
from typing import Any

from tests.support.session import Session

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
PLATE_TEXT = "A plate under 150 g, at least 50 g, fits in 120 x 80 x 40 mm, looks friendly"
LOAD: dict[str, Any] = {
    "support": {"kind": "flat_end"},
    "load": {
        "kind": "far_end",
        "force": {"magnitude": 10, "unit": "N"},
        "direction": {"kind": "any"},
    },
}


async def plate(s: Session) -> str:
    return (await s.call("build_variant", code=PLATE))["variant_id"]


async def settled(s: Session, **score: str) -> dict[str, Any]:
    card = await s.call("score_variant", **score)
    for _ in range(40):
        if not card["pending"]:
            return card
        card = await s.call("score_variant", **score)
    raise AssertionError(f"still pending: {card['pending']}")
