from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Final, cast

import pytest

from cad.auto.model import Stopped
from cad.auto.step import STILL_RUNNING
from cad.operations import auto, scorecards
from cad.scorecard.model import AgainstBrief
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import MAX_MEMBERS
from cad.variants.entry import VariantId
from tests.support.auto_session import PLA_CHOICE, running

if TYPE_CHECKING:
    from pathlib import Path

    from cad.operations.model import Tenant
    from cad.scorecard.material import ReportedScorecard
    from cad.variants.store import BuildResult
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


async def test_a_settling_revision_built_again_and_then_settled_counts_once(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.built_variant(SETTLING)
    brief_id, run_id = await running(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    monkeypatch.setattr(auto, "SETTLE_SECONDS", 0)
    monkeypatch.setattr(scorecards, "score_variant", fea_still_running)
    revised = await s.call("auto_revise", run_id=run_id, code=SETTLING)
    assert revised["settling"], revised
    await s.call("build_variant", code=SETTLING, brief_id=brief_id)
    monkeypatch.setattr(scorecards, "score_variant", settled)
    await s.call("auto_revise", run_id=run_id, code=SETTLING)
    state = s.run(run_id).state
    assert isinstance(state, Stopped), state
    assert "Builds tried: 1." in state.report, state.report


async def test_code_the_store_already_held_counts_as_a_build_and_starts_no_container(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.failed_variant(FIRST)
    brief_id, run_id = await running(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    await s.call("build_variant", code=FIRST, brief_id=brief_id, **PLA_CHOICE)
    await s.call("auto_ask", run_id=run_id, note="stuck")
    state = s.run(run_id).state
    assert isinstance(state, Stopped)
    assert "Builds tried: 1." in state.report, state.report
    assert s.meter.asked == []


@pytest.mark.parametrize("tool", ["build_variant", "auto_revise"])
async def test_a_build_whose_set_was_filled_while_it_ran_still_counts(
    s: Session, monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    s.built_variant(SETTLING)
    brief_id, run_id = await running(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    key = variant_sets.set_key(s.roots, brief_id)
    real = variant_sets.variants.build_variant

    def filled_while_it_ran(code: str, root: Path) -> BuildResult:
        built = real(code, root)
        for number in range(MAX_MEMBERS):
            other = f"result = 'another client filled slot {number + 1}'"
            variant_sets.join(s.roots.projects, key, other, VariantId(f"{number:016x}"))
        return built

    monkeypatch.setattr(variant_sets.variants, "build_variant", filled_while_it_ran)
    arguments = (
        {"brief_id": brief_id, **PLA_CHOICE} if tool == "build_variant" else {"run_id": run_id}
    )
    text = await s.refusal(tool, code=SETTLING, **arguments)
    assert "is stored" in text, text
    await s.call("auto_ask", run_id=run_id, note="stuck")
    state = s.run(run_id).state
    assert isinstance(state, Stopped)
    assert "Builds tried: 1." in state.report, state.report


async def test_a_build_whose_checks_still_run_when_the_person_stops_counts(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.built_variant(SETTLING)
    _, run_id = await running(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    monkeypatch.setattr(auto, "SETTLE_SECONDS", 0)

    def stopped_while_scoring(
        tenant: Tenant, scored: scorecards.ScoreVariantInput
    ) -> ReportedScorecard:
        auto.auto_stop(s.tenant, auto.StopInput(run_id=run_id))
        return fea_still_running(tenant, scored)

    monkeypatch.setattr(scorecards, "score_variant", stopped_while_scoring)
    await s.call("auto_revise", run_id=run_id, code=SETTLING)
    state = s.run(run_id).state
    assert isinstance(state, Stopped)
    assert "Builds tried: 1." in state.report, state.report
    assert STILL_RUNNING not in state.report, state.report


@pytest.mark.parametrize("tool", ["build_variant", "auto_revise"])
async def test_a_stop_while_a_build_runs_says_so_and_does_not_count_it(
    s: Session, monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    s.failed_variant(FIRST)
    s.failed_variant(SECOND)
    brief_id, run_id = await running(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    await s.call("build_variant", code=FIRST, brief_id=brief_id, **PLA_CHOICE)
    real = variant_sets.variants.build_variant

    def stopped_while_it_ran(code: str, root: Path) -> BuildResult:
        auto.auto_stop(s.tenant, auto.StopInput(run_id=run_id))
        return real(code, root)

    monkeypatch.setattr(variant_sets.variants, "build_variant", stopped_while_it_ran)
    arguments = (
        {"brief_id": brief_id, **PLA_CHOICE} if tool == "build_variant" else {"run_id": run_id}
    )
    await s.call(tool, code=SECOND, **arguments)
    state = s.run(run_id).state
    assert isinstance(state, Stopped)
    assert f"Builds tried: 1. {STILL_RUNNING}" in state.report, state.report


async def test_a_stop_with_no_build_running_names_none(s: Session) -> None:
    _, run_id = await running(s)
    stopped = auto.auto_stop(s.tenant, auto.StopInput(run_id=run_id)).run.state
    assert isinstance(stopped, Stopped)
    assert stopped.report == "The person stopped the run.\nNothing was built under the run."


def fea_still_running(_: Tenant, scored: scorecards.ScoreVariantInput) -> ReportedScorecard:
    assert scored.brief_id is not None
    basis = AgainstBrief(
        brief_id=scored.brief_id, decision_sha256="", requirements=(), unverified_requirements=()
    )
    return cast("ReportedScorecard", SimpleNamespace(pending=("fea",), basis=basis))


def settled(_: Tenant, scored: scorecards.ScoreVariantInput) -> ReportedScorecard:
    assert scored.brief_id is not None
    basis = AgainstBrief(
        brief_id=scored.brief_id, decision_sha256="", requirements=(), unverified_requirements=()
    )
    card = SimpleNamespace(pending=(), basis=basis, variant_id=scored.variant_id)
    return cast("ReportedScorecard", card)
