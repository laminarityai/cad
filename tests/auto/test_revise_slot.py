from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from auto.conftest import Session

pytestmark = pytest.mark.anyio

SOLID: Final = {"target": {"kind": "closed_solid"}, "quote": "less plastic"}
CHOICE: Final = {"material_key": "prusament-pla", "material_reason": "stiff and easy to print"}


@pytest.mark.parametrize("slot", [2, 4])
async def test_a_revision_into_a_slot_its_set_does_not_hold_is_refused_before_any_container(
    s: Session, started: list[str], slot: int
) -> None:
    brief_id = await s.confirmed("make the box use less plastic", SOLID)
    run = await s.start(brief_id=brief_id, **CHOICE)
    text = await s.refusal("auto_revise", run_id=run.run_id, code="result = None", slot=slot)
    assert f"SlotRefused: the variant set of brief {brief_id} holds no slot {slot}" in text
    assert "it holds no variant yet" in text
    assert "auto_start on the brief whose variant set holds it" in text
    assert started == []
    assert s.run(run.run_id).state.history == ()
