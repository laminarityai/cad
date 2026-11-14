from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from cad.auto.model import AllPass, Mark, NotChecked, Running, Standing, Stopped
from cad.auto.step import report
from cad.chat.auto_driver import AutoDriver
from cad.chat.log import StopReport

if TYPE_CHECKING:
    from tests.support.auto_session import Session

pytestmark = pytest.mark.anyio

NO_DOCKER: Final = "unix:///nonexistent/docker.sock"
ASA_CUBE: Final = (
    {
        "target": {"kind": "envelope", "edges": [{"magnitude": 20, "unit": "mm"}] * 3},
        "quote": "fits in a 20 mm cube",
    },
    {"target": {"kind": "made_of", "material": "asa"}, "quote": "ASA"},
    {
        "target": {"kind": "min_mass", "mass": {"magnitude": 50, "unit": "g"}},
        "quote": "at least 50 g",
    },
)
NOT_CHECKED: Final = (
    "asa has no density yet, so whether the mass can be at least 50 g within the whole "
    "20 x 20 x 20 mm box (8 cm³) is not checked until its density is researched"
)


async def test_a_run_on_a_material_with_no_density_yet_says_which_pair_is_not_checked(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed("A block that fits in a 20 mm cube, ASA, at least 50 g", *ASA_CUBE)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    run = await s.start(brief_id=brief_id)
    assert isinstance(run.state, Running)
    assert run.state.start.not_checked is not None
    assert run.state.start.not_checked.statement == NOT_CHECKED
    stopped = await s.call("auto_ask", run_id=run.run_id, note="which wall?")
    assert f"Not checked: {NOT_CHECKED}." in stopped["state"]["report"]
    ending = AutoDriver(s.tenant, run.run_id).ending()
    assert isinstance(ending, StopReport)
    assert f"Not checked: {NOT_CHECKED}." in ending.report
    assert isinstance(s.run(run.run_id).state, Stopped)


async def test_a_run_whose_material_has_a_density_records_no_unchecked_pair(s: Session) -> None:
    roomy = {
        "target": {"kind": "envelope", "edges": [{"magnitude": 50, "unit": "mm"}] * 3},
        "quote": "fits in a 50 mm cube",
    }
    pla = {"target": {"kind": "made_of", "material": "prusament-pla"}, "quote": "PLA"}
    text = "A block that fits in a 50 mm cube, PLA, at least 50 g"
    brief_id = await s.confirmed(text, roomy, pla, ASA_CUBE[2])
    run = await s.start(brief_id=brief_id)
    assert isinstance(run.state, Running)
    assert "not_checked" not in run.state.start.model_dump()


@pytest.mark.parametrize(
    ("mass", "shown"), [(Mark.UNKNOWN, True), (Mark.PASS_RESEARCHED, False), (Mark.FAIL, False)]
)
def test_the_stop_report_drops_the_unchecked_pair_once_research_gave_it_a_verdict(
    mass: Mark, shown: bool
) -> None:
    note = NotChecked(statement=NOT_CHECKED, requirements=("mass", "asa", "cube"))
    latest = Standing(
        revision=1,
        variant_id="v",
        code_sha256="c",
        built=True,
        marks=(("cube", Mark.PASS), ("mass", mass)),
    )
    reason = AllPass(researched=(), unverified=())
    for for_person in (False, True):
        said = report((latest,), 1, reason, for_person=for_person, not_checked=note)
        assert (f"Not checked: {NOT_CHECKED}." in said) is shown
