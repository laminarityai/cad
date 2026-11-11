from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from cad.briefs import store as briefs
from cad.checks import job_store
from cad.research.fetch import Page
from cad.research.submit import Question, ResearchAccepted, submit
from cad.tables.materials import load_materials

if TYPE_CHECKING:
    from tests.support.browser import Person
    from tests.support.session import Session

pytestmark = [pytest.mark.anyio, pytest.mark.docker]

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
URL = "https://example.org/silk-pla"
TEXT = "A plate in Prusament PETG under 150 g"
MADE_OF: dict[str, Any] = {
    "target": {"kind": "made_of", "material": "prusament-petg"},
    "quote": "Prusament PETG",
}
UNDER_150: dict[str, Any] = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}


async def propose(s: Session, *rows: dict[str, Any]) -> tuple[str, str]:
    created = await s.call("create_brief", text=TEXT)
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=list(rows))
    return created["brief_id"], created["project_id"]


async def confirmed(s: Session, person: Person, *rows: dict[str, Any]) -> str:
    person.answer = "confirm"
    brief_id, project_id = await propose(s, *rows)
    assert (await s.call("ask_to_confirm", project_id=project_id))["status"] == "answered"
    return brief_id


async def built(s: Session) -> str:
    return (await s.call("build_variant", code=PLATE))["variant_id"]


def jobs_path(s: Session, variant_id: str) -> Path:
    return s.roots.briefs.parent / "variants" / variant_id / job_store.JOBS


async def test_a_material_the_table_lacks_is_the_projects_own_row_and_asks_for_research(
    s: Session,
) -> None:
    created = await s.call("create_brief", text=TEXT)
    named = {**MADE_OF, "target": {"kind": "made_of", "material": "acme-silk-pla"}}
    proposed = await s.call(
        "propose_requirements", brief_id=created["brief_id"], requirements=[named, UNDER_150]
    )
    pin = proposed["requirements"][0]["requirement"]["target"]
    assert pin == {"kind": "made_of", "material": "project-acme-silk-pla"}
    [request] = proposed["research"]
    assert (request["brief_id"], request["key"], request["field"]) == (
        created["brief_id"],
        "project-acme-silk-pla",
        "density",
    )
    assert "submit_research" in request["instruction"]


async def test_a_loaded_requirement_asks_for_the_values_fea_reads(s: Session) -> None:
    created = await s.call("create_brief", text=TEXT)
    named = {**MADE_OF, "target": {"kind": "made_of", "material": "acme-silk-pla"}}
    load = {
        "support": {"kind": "flat_end"},
        "load": {
            "kind": "far_end",
            "force": {"magnitude": 10, "unit": "N"},
            "direction": {"kind": "any"},
        },
    }
    strong = {"target": {"kind": "min_safety_factor", "load": load, "factor": 2}, "quote": "PETG"}
    proposed = await s.call(
        "propose_requirements", brief_id=created["brief_id"], requirements=[named, strong]
    )
    assert [one["field"] for one in proposed["research"]] == [
        "density",
        "elastic_modulus",
        "poisson_ratio",
        "yield_strength",
    ]


async def test_a_material_the_table_cites_asks_for_nothing(s: Session) -> None:
    created = await s.call("create_brief", text=TEXT)
    proposed = await s.call(
        "propose_requirements", brief_id=created["brief_id"], requirements=[MADE_OF, UNDER_150]
    )
    assert "research" not in proposed


async def test_a_researched_project_row_decides_the_mass_labelled_researched(
    s: Session, person: Person
) -> None:
    named = {**MADE_OF, "target": {"kind": "made_of", "material": "acme-silk-pla"}}
    brief_id = await confirmed(s, person, named, UNDER_150)
    variant_id = await built(s)
    before = await s.call(
        "score_variant", variant_id=variant_id, material_key="acme-silk-pla", brief_id=brief_id
    )
    assert before["material"]["key"] == "project-acme-silk-pla"
    assert before["material"]["set_by"]["kind"] == "requirement"
    [request] = before["research"]
    assert (request["key"], request["field"]) == ("project-acme-silk-pla", "density")
    assert before["basis"]["requirements"][0]["verdict"] == "unknown"

    quote = "Density 1.24 g/cm3"
    project = briefs.read_brief(s.roots, brief_id).project
    question = Question(
        brief_id, project, "project-acme-silk-pla", "density", 1.24, "g/cm3", URL, quote
    )
    fetched = Page(URL, "Silk PLA data", f"Physical properties {quote}", "ab" * 32)
    answer = submit(load_materials(), s.roots.projects, question, fetcher=lambda _: fetched)
    assert isinstance(answer, ResearchAccepted)

    after = await s.call(
        "score_variant", variant_id=variant_id, material_key="acme-silk-pla", brief_id=brief_id
    )
    assert "research" not in after
    assert after["table_version"].endswith(f"+{project}@r1")
    mass = next(r for r in after["results"] if r["check_id"] == "mass")
    assert mass["verdict"] == "pass"
    assert mass["reads"] == [
        {"kind": "researched", "field": "density", "url": URL, "quote": quote, "sha256": "ab" * 32}
    ]
    [judged] = after["basis"]["requirements"]
    assert (judged["verdict"], judged["basis"]) == ("pass", "researched")


async def test_a_second_made_of_is_refused(s: Session) -> None:
    created = await s.call("create_brief", text=TEXT + " or Prusament PLA")
    other = {
        "target": {"kind": "made_of", "material": "prusament-pla"},
        "quote": "Prusament PLA",
    }
    text = await s.text(
        "propose_requirements", brief_id=created["brief_id"], requirements=[MADE_OF, other]
    )
    assert "at most one made_of" in text


async def test_the_page_says_a_made_of_fixes_the_material_and_gives_no_number_to_edit(
    s: Session,
) -> None:
    _, project_id = await propose(s, MADE_OF)
    await s.call("ask_to_confirm", project_id=project_id)
    status, page = s.get(s.person.url)
    assert status == 200
    assert "Fixes the material that scoring uses" in page
    assert "Made of Prusament PETG" in page
    assert "unverified" not in page


async def test_a_mismatched_material_key_is_refused_and_scores_nothing(
    s: Session, person: Person
) -> None:
    brief_id = await confirmed(s, person, MADE_OF, UNDER_150)
    variant_id = await built(s)
    text = await s.text(
        "score_variant", variant_id=variant_id, material_key="prusament-pla", brief_id=brief_id
    )
    assert "MaterialPinned" in text
    assert "prusament-petg" in text
    assert "No variant was scored" in text
    assert not jobs_path(s, variant_id).exists()


async def test_a_mismatch_is_refused_before_the_variant_is_opened_or_rebuilt(
    s: Session, person: Person
) -> None:
    brief_id = await confirmed(s, person, MADE_OF)
    text = await s.text(
        "score_variant",
        variant_id="0123456789abcdef",
        material_key="prusament-pla",
        brief_id=brief_id,
    )
    assert "MaterialPinned" in text


async def test_the_confirmed_key_scores_and_the_card_says_the_requirement_set_it(
    s: Session, person: Person
) -> None:
    brief_id = await confirmed(s, person, MADE_OF, UNDER_150)
    card = await s.call(
        "score_variant",
        variant_id=await built(s),
        material_key="prusament-petg",
        brief_id=brief_id,
    )
    pin = next(
        r
        for r in (await s.call("list_requirements", brief_id=brief_id))["proposals"][0][
            "requirements"
        ]
        if r["requirement"]["target"]["kind"] == "made_of"
    )
    assert card["material"] == {
        "key": "prusament-petg",
        "set_by": {
            "kind": "requirement",
            "requirement_id": pin["requirement"]["id"],
            "statement": "Made of prusament-petg",
        },
    }
    assert card["material_key"] == "prusament-petg"
    judged = card["basis"]["requirements"]
    assert [r["check_id"] for r in judged] == ["mass"]
    assert card["basis"]["unverified_requirements"] == []


async def test_an_unconfirmed_made_of_pins_nothing(s: Session) -> None:
    brief_id, _ = await propose(s, MADE_OF)
    card = await s.call(
        "score_variant", variant_id=await built(s), material_key="prusament-pla", brief_id=brief_id
    )
    assert card["material"]["key"] == "prusament-pla"
    assert card["material"]["set_by"]["kind"] == "agent_argument"


async def test_with_no_made_of_any_key_scores_and_the_card_says_the_agent_chose(
    s: Session, person: Person
) -> None:
    brief_id = await confirmed(s, person, UNDER_150)
    for key in ("prusament-pla", "prusament-petg"):
        card = await s.call(
            "score_variant", variant_id=await built(s), material_key=key, brief_id=brief_id
        )
        assert card["material"]["key"] == key
        assert card["material"]["set_by"]["kind"] == "agent_argument"
        assert "agent chose" in card["material"]["set_by"]["statement"]


async def test_a_score_with_no_brief_says_the_agent_chose(s: Session) -> None:
    card = await s.call("score_variant", variant_id=await built(s), material_key="prusament-pla")
    assert card["material"]["set_by"]["kind"] == "agent_argument"


async def test_a_score_with_a_key_the_table_lacks_asks_for_research_not_unknown(
    s: Session,
) -> None:
    card = await s.call("score_variant", variant_id=await built(s), material_key="acme-silk-pla")
    assert card["material_key"] == "project-acme-silk-pla"
    mass = next(r for r in card["results"] if r["check_id"] == "mass")
    assert mass["verdict"] == "unknown"
    [request] = card["research"]
    assert (request["key"], request["field"], request["brief_id"]) == (
        "project-acme-silk-pla",
        "density",
        None,
    )
