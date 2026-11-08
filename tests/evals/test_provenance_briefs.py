from pathlib import Path
from typing import Any

import pytest
from cards import BRIEF_TEXT, confirm, drafts, genuine_card, judged_card, reasons, trace
from confirmation import Misjudged, Superseded, Unconfirmed
from provenance import ConfirmedStep, Resolved, Unresolved
from tracking import RequirementOutcome, outcomes_of

from cad.briefs import store as briefs
from cad.briefs.store import ConfirmedSet
from cad.checks.result import Verdict
from cad.projects.model import new_project_id
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
def briefs_root(store: Path) -> Path:
    return store.parent / "briefs"


@pytest.fixture
def brief_id(briefs_root: Path) -> str:
    return briefs.create_brief(briefs_root, BRIEF_TEXT, new_project_id()).id


@pytest.fixture
def confirmed(briefs_root: Path, brief_id: str) -> ConfirmedSet:
    return confirm(briefs_root, brief_id, drafts(LIGHT, BOX, FRIENDLY))


def edited(card: Scorecard, change: dict[str, Any]) -> Scorecard:
    data = card.model_dump(mode="json")
    first = data["basis"]["requirements"][0]
    first.update(change.get("requirement", {}))
    first["comparisons"][0].update(change.get("comparison", {}))
    data["basis"].update(change.get("basis", {}))
    return Scorecard.model_validate(data)


def failures_of(card: Scorecard, store: Path) -> list[type]:
    return [type(failure) for failure in trace(card, store).failures]


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
    ],
)
def test_a_judgment_edited_on_the_card_is_misjudged(
    store: Path, confirmed: ConfirmedSet, change: dict[str, Any]
) -> None:
    card = edited(judged_card(confirmed), change)
    assert failures_of(card, store) == [Misjudged]


def test_a_card_scored_before_a_newer_confirmation_is_superseded(
    store: Path, briefs_root: Path, brief_id: str, confirmed: ConfirmedSet
) -> None:
    card = judged_card(confirmed)
    confirm(briefs_root, brief_id, drafts(LIGHT))
    traced = trace(card, store)
    assert [type(failure) for failure in traced.failures] == [Superseded]
    assert all(isinstance(one.outcome, Resolved) for one in traced.numbers)


def test_an_awaiting_card_passes_until_its_brief_is_confirmed_and_is_then_superseded(
    store: Path, briefs_root: Path, brief_id: str
) -> None:
    card = genuine_card(basis=AwaitingConfirmation(brief_id=brief_id))
    assert failures_of(card, store) == []
    confirm(briefs_root, brief_id, drafts(LIGHT))
    assert failures_of(card, store) == [Superseded]


def test_a_brief_store_without_a_key_is_unconfirmed_and_no_key_is_made(
    store: Path, briefs_root: Path, confirmed: ConfirmedSet
) -> None:
    key.key_path(briefs_root).unlink()
    card = judged_card(confirmed)
    assert failures_of(card, store) == [Unconfirmed]
    assert reasons(trace(card, store), Unresolved, FIRST_LIMIT) != []
    assert not key.key_path(briefs_root).exists()


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
    store: Path, briefs_root: Path, confirmed: ConfirmedSet
) -> None:
    (briefs_root / confirmed.brief_id / "decisions" / "0001.signed").write_text("{}")
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
