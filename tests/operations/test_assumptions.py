import pytest

from cad.auto.gate import watermark
from cad.projects.model import ProjectId
from tests.support.session import Session

pytestmark = pytest.mark.anyio

MASS = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 120, "unit": "g"}},
    "why": "ZZ-LIGHT-WHY a light part prints fast",
}


async def test_an_assumptions_only_call_writes_no_proposal_and_leaves_auto_running(
    s: Session,
) -> None:
    brief = await s.proposed(s.rows.under_150)
    before = watermark(s.roots, ProjectId(brief.project_id))
    shown = await s.call("propose_requirements", brief_id=brief.brief_id, assumptions=[MASS])
    after = watermark(s.roots, ProjectId(brief.project_id))
    assert before == after
    assert shown["proposal"] == 1 and shown["status"] == "proposed"
    assert [one["why"] for one in shown["assumptions"]] == [MASS["why"]]
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    assert len(listed["proposals"]) == 1
    assert [one["check"] for one in listed["assumptions"]] == ["mass"]


async def test_a_call_with_neither_requirements_nor_assumptions_is_refused(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    text = await s.text("propose_requirements", brief_id=brief.brief_id)
    assert "pass requirements, assumptions or both" in text


async def test_an_assumption_alone_proposes_nothing_for_a_brief_with_no_proposal(
    s: Session,
) -> None:
    created = await s.call("create_brief", text=s.rows.text)
    shown = await s.call("propose_requirements", brief_id=created["brief_id"], assumptions=[MASS])
    assert (shown["proposal"], shown["status"], shown["requirements"]) == (None, None, [])
    asked = await s.call("ask_to_confirm", project_id=created["project_id"])
    assert (asked["status"], s.person.urls) == ("nothing_to_confirm", [])


async def test_an_assumption_is_never_on_the_confirmation_page(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.call("propose_requirements", brief_id=brief.brief_id, assumptions=[MASS])
    await s.ask(brief)
    body = s.get(s.person.url)[1]
    assert "ZZ-LIGHT-WHY" not in body and "120 g" not in body
    assert "Mass at most 150 g" in body


async def test_each_call_replaces_the_assumptions_and_an_empty_list_clears_them(
    s: Session,
) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.call("propose_requirements", brief_id=brief.brief_id, assumptions=[MASS])
    kept = await s.call(
        "propose_requirements", brief_id=brief.brief_id, requirements=[s.rows.under_150]
    )
    assert len(kept["assumptions"]) == 1
    cleared = await s.call("propose_requirements", brief_id=brief.brief_id, assumptions=[])
    assert "assumptions" not in cleared
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    assert "assumptions" not in listed


async def test_an_assumption_for_a_target_with_no_number_is_refused(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    text = await s.text(
        "propose_requirements",
        brief_id=brief.brief_id,
        assumptions=[{"target": {"kind": "closed_solid"}, "why": "x"}],
    )
    assert "assumptions[0]" in text
