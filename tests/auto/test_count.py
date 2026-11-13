from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from cad.auto.model import Stopped
from tests.support.auto_session import PLA_CHOICE, running

if TYPE_CHECKING:
    from tests.support.auto_session import Session

pytestmark = pytest.mark.anyio

NO_DOCKER: Final = "unix:///nonexistent/docker.sock"
FIRST: Final = "raise NameError('the first option under the run')"
SECOND: Final = "raise NameError('the second option under the run')"


async def test_the_stop_report_counts_every_build_under_the_run_once(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.failed_variant(FIRST)
    s.failed_variant(SECOND)
    brief_id, run_id = await running(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    for _ in range(2):
        await s.call("build_variant", code=FIRST, brief_id=brief_id, **PLA_CHOICE)
    await s.call("auto_revise", run_id=run_id, code=SECOND)
    await s.call("auto_revise", run_id=run_id, code=FIRST)
    await s.call("auto_ask", run_id=run_id, note="stuck")
    state = s.run(run_id).state
    assert isinstance(state, Stopped)
    assert "Builds tried: 2." in state.report, state.report
    assert s.meter.asked == []
