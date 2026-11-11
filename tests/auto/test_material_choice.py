from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from cad.auto.log import run_dir
from cad.briefs.store import read_brief
from cad.scorecard.material import AGENT_CHOSE

if TYPE_CHECKING:
    from tests.support.auto_session import Session

pytestmark = pytest.mark.anyio

PLATE: Final = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
TEXT: Final = "A plate under 150 g"
UNDER_150: Final = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}
REASON: Final = "PLA is light and prints without warping"


@pytest.mark.parametrize(
    "arguments",
    [{}, {"material_key": "prusament-pla"}, {"material_reason": REASON}],
    ids=["neither", "key only", "reason only"],
)
async def test_a_start_with_no_confirmed_material_and_no_choice_is_refused_never_asking_the_person(
    s: Session, arguments: dict[str, str]
) -> None:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    text = await s.refusal("auto_start", brief_id=brief_id, **arguments)
    assert "RunRefused" in text
    assert "Never ask the person to choose" in text
    project = read_brief(s.roots, brief_id).project
    assert not (s.roots.projects / project / "auto").exists()


@pytest.mark.docker
async def test_a_start_with_a_choice_records_it_on_every_revision_it_builds(s: Session) -> None:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    run = await s.start(brief_id=brief_id, material_key="prusament-pla", material_reason=REASON)
    assert run.state.start.material_reason == REASON
    assert run_dir(s.roots, run.run_id).is_dir()
    revised = await s.call("auto_revise", run_id=run.run_id, code=PLATE)
    while revised["settling"]:
        revised = await s.call("auto_revise", run_id=run.run_id, code=PLATE)
    project = read_brief(s.roots, brief_id).project
    shown = await s.call("variant_set", project_id=project, brief_id=brief_id)
    [member] = shown["members"]
    assert member["material"] == {
        "key": "prusament-pla",
        "set_by": {"kind": "agent_argument", "statement": AGENT_CHOSE, "reason": REASON},
    }
