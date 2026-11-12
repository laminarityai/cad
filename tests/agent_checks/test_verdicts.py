"""An approved agent-written check decides its requirement on a scored card, labelled, and only
once the person approved it. The sandbox runs are given: test_turned_sandbox.py runs them."""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from cad.agent_checks import turned, verdicts
from cad.agent_checks.model import AgentCheck
from cad.briefs.store import ConfirmedSet
from cad.checks.result import Verdict
from cad.context_parts.model import Outcome
from cad.operations.agent_checks import with_agent_checks
from cad.records.roots import Roots
from cad.sandbox.host import SandboxUnavailable
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.scorecard import material
from cad.scorecard.model import AGENT_CHECK, AgainstBrief, AgentChecked, Unverified
from cad.tables.materials import UNITS
from cad.variants import entry
from tests.support.agent_checks import answer, write
from tests.support.cards import BREP, genuine_card, judged_card, table

pytestmark = pytest.mark.usefixtures("no_sandbox")
CODE = "result = Box(20, 5, 2)"


type Run = Callable[[bytes, Sequence[AgentCheck]], tuple[turned.Measured, ...]]


def deflected(y: float) -> Run:
    """A sandbox whose turned and plain runs agree on a 2 mm by 20 mm arm deflected y mm."""

    def on_variant(brep: bytes, checks: Sequence[AgentCheck]) -> tuple[turned.Measured, ...]:
        assert brep == BREP
        values = {"h": 2.0, "l": 20.0, "y": y}
        return tuple({k: UNITS.Quantity(v, "mm") for k, v in values.items()} for _ in checks)

    return on_variant


def scored(
    roots: Roots, variants: Path, confirmed: ConfirmedSet, *, run: bool = True
) -> AgainstBrief:
    vid = entry.variant_id(CODE, image_tag(BUILD))
    entry.save(variants, vid, CODE, Build(outcome=Built(), output=""), BREP)
    card = judged_card(confirmed).model_copy(update={"variant_id": vid})
    reported = material.reported(card, confirmed)
    found = with_agent_checks(reported, roots, variants, confirmed, table(), run=run).basis
    assert isinstance(found, AgainstBrief)
    return found


@pytest.mark.parametrize(
    ("y", "verdict", "strain"), [(1.0, Verdict.PASS, 0.75), (4.0, Verdict.FAIL, 3.0)]
)
def test_an_approved_check_decides_its_requirement_with_its_label(
    roots: Roots,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    y: float,
    verdict: Verdict,
    strain: float,
) -> None:
    brief_id, stored = write(roots)
    confirmed = answer(roots, brief_id, stored, "confirmed")
    monkeypatch.setattr(turned, "on_variant", deflected(y))
    basis = scored(roots, tmp_path / "variants", confirmed)
    [row] = basis.requirements
    assert isinstance(row, AgentChecked)
    assert (row.label, row.verdict, row.check_sha256) == (AGENT_CHECK, verdict, stored.sha256)
    assert row.value is not None and float(row.value.m_as("percent")) == pytest.approx(strain)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert [one.read for one in row.inputs][1:] == ["geometry:h", "geometry:l", "geometry:y"]
    assert basis.unverified_requirements == ()
    assert basis.agent_checked_requirements == (row.requirement_id,)


@pytest.mark.parametrize("check", ["declined", "waiting"])
def test_a_check_the_person_has_not_approved_decides_nothing(
    roots: Roots, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, check: Outcome
) -> None:
    brief_id, stored = write(roots)
    confirmed = answer(roots, brief_id, stored, check)

    def unreachable(brep: bytes, checks: Sequence[AgentCheck]) -> tuple[turned.Measured, ...]:
        raise AssertionError("an unapproved check never runs")

    monkeypatch.setattr(turned, "on_variant", unreachable)
    basis = scored(roots, tmp_path / "variants", confirmed)
    [row] = basis.requirements
    assert isinstance(row, Unverified)
    assert basis.unverified_requirements == (row.requirement_id,)
    assert basis.agent_checked_requirements == ()


def test_a_card_read_later_shows_the_stored_run_and_runs_no_code(
    roots: Roots, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, stored = write(roots)
    confirmed = answer(roots, brief_id, stored, "confirmed")
    monkeypatch.setattr(turned, "on_variant", deflected(1.0))
    first = scored(roots, tmp_path / "variants", confirmed)

    def unreachable(brep: bytes, checks: Sequence[AgentCheck]) -> tuple[turned.Measured, ...]:
        raise AssertionError("the stored run is read, not run again")

    monkeypatch.setattr(turned, "on_variant", unreachable)
    assert scored(roots, tmp_path / "variants", confirmed, run=False) == first
    assert scored(roots, tmp_path / "variants", confirmed) == first


def test_a_card_read_before_any_score_ran_the_check_is_unknown(
    roots: Roots, tmp_path: Path
) -> None:
    brief_id, stored = write(roots)
    confirmed = answer(roots, brief_id, stored, "confirmed")
    [row] = scored(roots, tmp_path / "variants", confirmed, run=False).requirements
    assert isinstance(row, AgentChecked)
    assert (row.verdict, row.reason, row.value) == (Verdict.UNKNOWN, verdicts.NOT_RUN, None)


def test_code_whose_answers_change_with_the_turn_leaves_it_unknown(
    roots: Roots, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, stored = write(roots)
    confirmed = answer(roots, brief_id, stored, "confirmed")

    def unsound(brep: bytes, checks: Sequence[AgentCheck]) -> tuple[turned.Unsound, ...]:
        return tuple(turned.Unsound("h was 2 and then 3 mm") for _ in checks)

    monkeypatch.setattr(turned, "on_variant", unsound)
    [row] = scored(roots, tmp_path / "variants", confirmed).requirements
    assert isinstance(row, AgentChecked) and row.verdict is Verdict.UNKNOWN
    assert "cannot be trusted on this part: h was 2 and then 3 mm" in row.reason


def test_a_sandbox_that_is_down_keeps_nothing_so_the_next_score_runs_it(
    roots: Roots, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id, stored = write(roots)
    confirmed = answer(roots, brief_id, stored, "confirmed")

    def down(brep: bytes, checks: Sequence[AgentCheck]) -> tuple[turned.Measured, ...]:
        raise SandboxUnavailable("docker is not running")

    monkeypatch.setattr(turned, "on_variant", down)
    [row] = scored(roots, tmp_path / "variants", confirmed).requirements
    assert isinstance(row, AgentChecked) and row.reason == verdicts.NOT_RUN
    monkeypatch.setattr(turned, "on_variant", deflected(1.0))
    [row] = scored(roots, tmp_path / "variants", confirmed).requirements
    assert isinstance(row, AgentChecked) and row.verdict is Verdict.PASS


def test_a_card_scored_with_no_brief_is_left_alone(roots: Roots, tmp_path: Path) -> None:
    card = material.reported(genuine_card(), None)
    assert with_agent_checks(card, roots, tmp_path, None, table(), run=True) == card
