from pathlib import Path
from typing import Any

import pytest
from cards import (
    BRIEF_TEXT,
    confirm,
    confirm_on_page,
    drafts,
    genuine_card,
    judged_card,
    reasons,
    roots_beside,
    trace,
)
from confirmation import Misjudged, Superseded, Unconfirmed
from provenance import ConfirmedStep, Resolved, Unresolved
from tracking import RequirementOutcome, outcomes_of

from cad.briefs import store as briefs
from cad.briefs.store import ConfirmedSet
from cad.checks.result import Verdict
from cad.confirmations import answers
from cad.projects.model import ProjectId, new_project_id
from cad.records.roots import Roots
from cad.scorecard.model import AwaitingConfirmation, Scorecard
from cad.variants import key

LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}, "under 150 g")
BOX = (
    {"kind": "envelope", "edges": [{"magnitude": e, "unit": "mm"} for e in (120, 80, 40)]},
    "fits in 120 x 80 x 40 mm",
)
FRIENDLY = ({"kind": "unchecked", "statement": "looks friendly"}, "looks friendly")
FIRST_LIMIT = "basis.requirements[0].comparisons[0].limit"


@pytest.fixture
def roots(store: Path) -> Roots:
    return roots_beside(store)


@pytest.fixture
def brief_id(roots: Roots) -> str:
    return briefs.create_brief(roots, BRIEF_TEXT, new_project_id()).id


@pytest.fixture
def confirmed(roots: Roots, brief_id: str) -> ConfirmedSet:
    return confirm(roots, brief_id, drafts(LIGHT, BOX, FRIENDLY))


def edited(card: Scorecard, change: dict[str, Any]) -> Scorecard:
    data = card.model_dump(mode="json")
    first = data["basis"]["requirements"][0]
    first.update(change.get("requirement", {}))
    first["comparisons"][0].update(change.get("comparison", {}))
    data["basis"].update(change.get("basis", {}))
    if change.get("drop"):
        del data["basis"]["requirements"][0]
    return Scorecard.model_validate(data)


def failures_of(card: Scorecard, store: Path) -> list[type]:
    return [type(failure) for failure in trace(card, store).failures]


def project_of(roots: Roots, brief_id: str) -> ProjectId:
    return briefs.read_brief(roots, brief_id).project


def test_every_confirmed_limit_resolves_to_the_decision_that_confirmed_it(
    store: Path, confirmed: ConfirmedSet
) -> None:
    traced = trace(judged_card(confirmed), store)
    assert traced.failures == ()
    assert all(isinstance(one.outcome, Resolved) for one in traced.numbers)
    limits = {one.label: one.outcome for one in traced.numbers if one.label.startswith("basis")}
    light = confirmed.requirements[0].id
    assert len(limits) == 4
    assert limits[FIRST_LIMIT] == Resolved(
        (ConfirmedStep(confirmed.brief_id, confirmed.decision_sha256, light, "Mass at most 150 g"),)
    )


def test_a_limit_confirmed_on_the_page_resolves_to_the_page_answer(
    store: Path, roots: Roots, brief_id: str
) -> None:
    confirmed = confirm_on_page(roots, brief_id, drafts(LIGHT, BOX, FRIENDLY))
    [(answer_sha256, _)] = answers.read_ledger(roots.projects, project_of(roots, brief_id)).answers
    traced = trace(judged_card(confirmed), store)
    light = confirmed.requirements[0].id
    assert traced.failures == ()
    assert confirmed.decision_sha256 == answer_sha256
    assert {one.outcome for one in traced.numbers if one.label == FIRST_LIMIT} == {
        Resolved((ConfirmedStep(confirmed.brief_id, answer_sha256, light, "Mass at most 150 g"),))
    }


def test_a_tampered_page_answer_is_unconfirmed(store: Path, roots: Roots, brief_id: str) -> None:
    card = judged_card(confirm_on_page(roots, brief_id, drafts(LIGHT)))
    [path] = roots.projects.glob("*/answers/0001.signed")
    path.write_bytes(path.read_bytes().replace(b"confirmed", b"declined"))
    assert failures_of(card, store) == [Unconfirmed]


def test_a_limit_edited_on_the_card_is_unresolved_and_the_card_misjudged(
    store: Path, confirmed: ConfirmedSet
) -> None:
    card = edited(
        judged_card(confirmed), {"comparison": {"limit": {"magnitude": 200, "unit": "g"}}}
    )
    traced = trace(card, store)
    assert reasons(traced, Unresolved, FIRST_LIMIT) != []
    assert Misjudged in failures_of(card, store)


@pytest.mark.parametrize(
    "change",
    [
        {"requirement": {"verdict": "pass"}, "comparison": {"verdict": "pass"}},
        {"requirement": {"check_id": "extents"}},
        {"requirement": {"statement": "Mass at most 1 t"}},
        {"drop": True},
    ],
)
def test_a_judgment_edited_on_the_card_is_misjudged(
    store: Path, confirmed: ConfirmedSet, change: dict[str, Any]
) -> None:
    card = edited(judged_card(confirmed), change)
    assert failures_of(card, store) == [Misjudged]


def test_a_card_scored_before_a_newer_confirmation_is_superseded(
    store: Path, roots: Roots, brief_id: str, confirmed: ConfirmedSet
) -> None:
    card = judged_card(confirmed)
    confirm(roots, brief_id, drafts(LIGHT))
    traced = trace(card, store)
    assert [type(failure) for failure in traced.failures] == [Superseded]
    assert all(isinstance(one.outcome, Resolved) for one in traced.numbers)


def test_an_awaiting_card_passes_until_its_brief_is_confirmed_and_is_then_superseded(
    store: Path, roots: Roots, brief_id: str
) -> None:
    card = genuine_card(basis=AwaitingConfirmation(brief_id=brief_id))
    assert failures_of(card, store) == []
    confirm(roots, brief_id, drafts(LIGHT))
    assert failures_of(card, store) == [Superseded]


def test_a_brief_store_without_a_key_is_unconfirmed_and_no_key_is_made(
    store: Path, roots: Roots, confirmed: ConfirmedSet
) -> None:
    key.key_path(roots.briefs).unlink()
    card = judged_card(confirmed)
    assert failures_of(card, store) == [Unconfirmed]
    assert reasons(trace(card, store), Unresolved, FIRST_LIMIT) != []
    assert not key.key_path(roots.briefs).exists()


@pytest.mark.parametrize(
    "change",
    [
        {"basis": {"decision_sha256": "e" * 64}},
        {"basis": {"brief_id": "0123456789abcdef"}},
    ],
)
def test_a_decision_the_store_cannot_show_is_unconfirmed(
    store: Path, confirmed: ConfirmedSet, change: dict[str, Any]
) -> None:
    assert failures_of(edited(judged_card(confirmed), change), store) == [Unconfirmed]


def test_a_tampered_brief_is_unconfirmed(
    store: Path, roots: Roots, confirmed: ConfirmedSet
) -> None:
    (roots.briefs / confirmed.brief_id / "decisions" / "0001.signed").write_text("{}")
    assert failures_of(judged_card(confirmed), store) == [Unconfirmed]


def test_each_requirement_is_one_outcome_reviewed_when_a_check_decided_it(
    confirmed: ConfirmedSet,
) -> None:
    card = judged_card(confirmed)
    light, box, friendly = (r.id for r in confirmed.requirements)
    assert outcomes_of(card) == (
        RequirementOutcome(light, Verdict.FAIL, reviewed=True),
        RequirementOutcome(box, Verdict.UNKNOWN, reviewed=True),
        RequirementOutcome(friendly, Verdict.UNKNOWN, reviewed=False),
    )
    assert outcomes_of(genuine_card(basis=AwaitingConfirmation(brief_id=confirmed.brief_id))) == ()
