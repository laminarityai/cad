from datetime import UTC, datetime
from pathlib import Path

import pytest
from cards import (
    confirm_on_page,
    drafts,
    genuine_card,
    genuine_result,
    roots_beside,
    trace,
)
from fitted import Unfitted
from trace_store import SPEC_BY_ID

from cad.briefs import store as briefs
from cad.confirmations import answers
from cad.confirmations.answers import ItemAnswer, PageAnswer
from cad.context_parts import store as parts
from cad.context_parts.ingest import Facts
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.scorecard.model import Basis, Scorecard
from cad.scorecard.requirements import against
from cad.variants import entry

TEXT = "A clip that slides onto the rail, at least 0.2 mm clear of it"
RAIL = Facts(solids=1, volume_mm3=64800.0, box_min=(0, 0, 0), box_max=(300, 18, 12))
FORGED = "part-" + "0" * 16


@pytest.fixture
def roots(store: Path) -> Roots:
    return roots_beside(store)


@pytest.fixture
def brief_id(roots: Roots) -> str:
    return briefs.create_brief(roots, TEXT, new_project_id()).id


def rail(roots: Roots, store: Path, brief_id: str, *, confirmed: bool) -> str:
    code = "result = Box(300, 18, 12)\n"
    vid = entry.variant_id(code, image_tag(BUILD))
    entry.save(store, vid, code, Build(outcome=Built(), output=""), b"a rail brep")
    stored = parts.propose(roots, store, brief_id, "the rail", "rail", vid, lambda _: RAIL)
    if confirmed:
        item = ItemAnswer(item=stored.ref, verdict="confirmed", edits=())
        project = stored.record.project
        page = PageAnswer(project=project, answers=(item,), decided_at=datetime.now(UTC))
        assert answers.append_answer(roots.projects, project, page)
    return stored.record.id


def fitted_card(roots: Roots, brief_id: str, part: str, instance: str) -> Scorecard:
    clear = {"kind": "min_clearance", "part": part, "clearance": {"magnitude": 0.2, "unit": "mm"}}
    confirmed = confirm_on_page(roots, brief_id, drafts((clear, "at least 0.2 mm clear of it")))
    measured = genuine_result(SPEC_BY_ID["fit"]).model_copy(update={"instance": instance})
    card = genuine_card()
    card = card.model_copy(update={"results": (*card.results, measured)})
    basis: Basis = against(confirmed)(card.finished)
    return card.model_copy(update={"basis": basis})


def test_a_fit_against_a_confirmed_part_traces_with_no_failure(
    roots: Roots, store: Path, brief_id: str
) -> None:
    part = rail(roots, store, brief_id, confirmed=True)
    traced = trace(fitted_card(roots, brief_id, part, part), store)
    assert traced.failures == ()
    assert "fit.min_clearance" in [one.label for one in traced.numbers]


def test_a_fit_naming_a_part_the_project_never_confirmed_fails_the_card(
    roots: Roots, store: Path, brief_id: str
) -> None:
    part = rail(roots, store, brief_id, confirmed=True)
    traced = trace(fitted_card(roots, brief_id, part, FORGED), store)
    (failure,) = traced.failures
    assert isinstance(failure, Unfitted)
    assert failure.reason.startswith(f"the fit result for {FORGED} names no part confirmed")


def test_a_fit_against_a_part_still_waiting_on_the_page_fails_the_card(
    roots: Roots, store: Path, brief_id: str
) -> None:
    part = rail(roots, store, brief_id, confirmed=False)
    traced = trace(fitted_card(roots, brief_id, part, part), store)
    assert [type(one) for one in traced.failures] == [Unfitted]
