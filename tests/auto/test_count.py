from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Final, cast

import pytest

from cad.auto.model import Stopped
from cad.operations import auto, scorecards
from cad.scorecard.model import AgainstBrief
from tests.support.auto_session import PLA_CHOICE, running

if TYPE_CHECKING:
    from cad.operations.model import Tenant
    from cad.scorecard.material import ReportedScorecard
    from tests.support.auto_session import Session

pytestmark = pytest.mark.anyio

NO_DOCKER: Final = "unix:///nonexistent/docker.sock"
FIRST: Final = "raise NameError('the first option under the run')"
SECOND: Final = "raise NameError('the second option under the run')"
SETTLING: Final = "result = 'a part whose checks are still running'"
THIRD: Final = "raise NameError('the third option, built only by build_variant')"


async def test_the_stop_report_counts_every_build_under_the_run_once(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.failed_variant(FIRST)
    s.failed_variant(SECOND)
    s.failed_variant(THIRD)
    brief_id, run_id = await running(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    for _ in range(2):
        await s.call("build_variant", code=FIRST, brief_id=brief_id, **PLA_CHOICE)
    await s.call("build_variant", code=THIRD, brief_id=brief_id, **PLA_CHOICE)
    await s.call("auto_revise", run_id=run_id, code=SECOND)
    await s.call("auto_revise", run_id=run_id, code=FIRST)
    await s.call("auto_ask", run_id=run_id, note="stuck")
    state = s.run(run_id).state
    assert isinstance(state, Stopped)
    assert "Builds tried: 3." in state.report, state.report
    assert s.meter.asked == []


async def test_a_build_whose_checks_still_run_counts_once_when_the_run_stops(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.built_variant(SETTLING)
    _, run_id = await running(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    monkeypatch.setattr(scorecards, "score_variant", fea_still_running)
    monkeypatch.setattr(auto, "SETTLE_SECONDS", 0)
    for _ in range(2):
        revised = await s.call("auto_revise", run_id=run_id, code=SETTLING)
        assert revised["settling"], revised
    await s.call("auto_ask", run_id=run_id, note="stuck")
    state = s.run(run_id).state
    assert isinstance(state, Stopped)
    assert "Builds tried: 1." in state.report, state.report


def fea_still_running(_: Tenant, scored: scorecards.ScoreVariantInput) -> ReportedScorecard:
    assert scored.brief_id is not None
    basis = AgainstBrief(
        brief_id=scored.brief_id, decision_sha256="", requirements=(), unverified_requirements=()
    )
    return cast("ReportedScorecard", SimpleNamespace(pending=("fea",), basis=basis))
