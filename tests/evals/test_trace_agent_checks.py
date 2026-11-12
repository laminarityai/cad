"""The tracer counts an approved agent-written check's requirements on a line of their own, in
neither headline number, and refuses a card whose agent-written check the person did not approve."""

from pathlib import Path

import pytest
from trace_store import main

from cad.agent_checks import probes
from cad.agent_checks.gates import Shaped
from cad.agent_checks.model import CheckDraft
from cad.checks.result import Verdict
from cad.context_parts.model import Outcome
from cad.scorecard.model import AgainstBrief, Scorecard
from tests.support.agent_checks import answer, write
from tests.support.cards import judged_card, lines, roots_beside, transcript_of, write_transcript
from tests.support.scorecard import agent_checked


@pytest.fixture(autouse=True)
def no_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    def passes(draft: CheckDraft, shaped: Shaped) -> None:
        return None

    monkeypatch.setattr(probes, "repeat_and_turn", passes)


def decided_by_the_agent_check(store: Path, approval: Outcome) -> Scorecard:
    roots = roots_beside(store)
    brief_id, stored = write(roots)
    card = judged_card(answer(roots, brief_id, stored, approval))
    basis = card.basis
    assert isinstance(basis, AgainstBrief)
    [unverified] = basis.requirements
    row = agent_checked(unverified.requirement_id, Verdict.PASS).model_copy(
        update={"check_sha256": stored.sha256, "statement": unverified.statement}
    )
    held = basis.model_copy(
        update={
            "requirements": (row,),
            "unverified_requirements": (),
            "agent_checked_requirements": (row.requirement_id,),
        }
    )
    return card.model_copy(update={"basis": held})


def arguments(store: Path) -> list[str]:
    roots = roots_beside(store)
    return [
        str(transcript_of(store)),
        "--root",
        str(store),
        "--briefs-root",
        str(roots.briefs),
        "--projects-root",
        str(roots.projects),
    ]


def test_an_approved_agent_checks_requirement_counts_apart_and_in_neither_headline(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_transcript(store, decided_by_the_agent_check(store, "confirmed"))
    assert main([*arguments(store), "--require-judged"]) == 0
    out = lines(capsys)
    assert "misjudged: 0" in out
    assert "numbers of agent-written checks the person approved: 1" in out
    assert "strict pass rate: 0/1 (0%)" in out
    assert "requirements covered by reviewed checks: 0/1 (0%)" in out
    assert "requirements covered by agent-written checks the person approved: 1/1 (100%)" in out


@pytest.mark.parametrize("approval", ["declined", "waiting"])
def test_a_card_whose_agent_written_check_the_person_did_not_approve_is_misjudged(
    store: Path, capsys: pytest.CaptureFixture[str], approval: Outcome
) -> None:
    write_transcript(store, decided_by_the_agent_check(store, approval))
    assert main(arguments(store)) == 1
    out = lines(capsys)
    assert "MISJUDGED" in out
    assert "an agent-written check the person did not approve" in out
