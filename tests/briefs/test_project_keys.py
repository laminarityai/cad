from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from cad.briefs import store as briefs
from cad.research.fetch import Page
from cad.research.submit import Question, ResearchAccepted, submit
from cad.tables.materials import TABLE_PATH, load_materials

if TYPE_CHECKING:
    from tests.support.browser import Person
    from tests.support.session import Session

pytestmark = pytest.mark.anyio

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
URL = "https://example.org/acme-matte-pla"
TEXT = "A plate printed in Prusament PLA under 150 g"
SHADOWS = ["project-prusament-pla", "project-project-prusament-pla"]
CITED = "prusament-pla already has a cited density, which research never replaces"
UNDER_150: dict[str, Any] = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}


def made_of(material: str, quote: str = "Prusament PLA") -> dict[str, Any]:
    return {"target": {"kind": "made_of", "material": material}, "quote": quote}


@pytest.mark.parametrize("key", SHADOWS)
async def test_a_project_key_for_a_table_row_proposes_the_table_row(s: Session, key: str) -> None:
    created = await s.call("create_brief", text=TEXT)
    proposed = await s.call(
        "propose_requirements", brief_id=created["brief_id"], requirements=[made_of(key), UNDER_150]
    )
    pin = proposed["requirements"][0]["requirement"]["target"]
    assert pin == {"kind": "made_of", "material": "prusament-pla"}
    assert "research" not in proposed


@pytest.mark.parametrize("key", SHADOWS)
@pytest.mark.docker
async def test_scoring_a_project_key_for_a_table_row_reads_the_cited_row(
    s: Session, key: str
) -> None:
    variant_id = (await s.call("build_variant", code=PLATE))["variant_id"]
    card = await s.call("score_variant", variant_id=variant_id, material_key=key)
    assert card["material"]["key"] == "prusament-pla"
    mass = next(r for r in card["results"] if r["check_id"] == "mass")
    assert mass["reads"] == [{"kind": "cited", "field": "density"}]
    assert "research" not in card


@pytest.mark.parametrize("key", SHADOWS)
async def test_research_for_a_project_key_for_a_table_row_is_refused(s: Session, key: str) -> None:
    created = await s.call("create_brief", text=TEXT)
    answer = await s.call(
        "submit_research",
        brief_id=created["brief_id"],
        key=key,
        field="density",
        value=1.28,
        unit="g/cm3",
        url="https://example.org/petg",
        quote="Density 1.28 g/cm3",
    )
    assert answer["result"]["kind"] == "refused"
    assert CITED in answer["result"]["reason"]
    assert not (s.roots.projects / created["project_id"] / "research").exists()


@pytest.mark.parametrize("key", ["Prusament PLA", "prusament pla"])
async def test_research_for_a_key_that_is_not_lowercase_words_is_refused(
    s: Session, key: str
) -> None:
    created = await s.call("create_brief", text=TEXT)
    text = await s.text(
        "submit_research",
        brief_id=created["brief_id"],
        key=key,
        field="density",
        value=1.24,
        unit="g/cm3",
        url="https://example.org/pla",
        quote="Density 1.24 g/cm3",
    )
    assert "pattern" in text
    assert "accepted" not in text


async def propose_esun(s: Session) -> dict[str, Any]:
    created = await s.call("create_brief", text="A plate in eSUN PLA Silk under 150 g")
    await s.call(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[made_of("esun-pla-silk", "eSUN PLA Silk"), UNDER_150],
    )
    return created


async def test_the_page_names_a_project_material_plainly(s: Session) -> None:
    created = await propose_esun(s)
    await s.call("ask_to_confirm", project_id=created["project_id"])
    _, page = s.get(s.person.url)
    assert "Made of esun-pla-silk" in page
    assert "project-" not in page


@pytest.mark.docker
async def test_the_card_names_a_project_material_plainly(s: Session, person: Person) -> None:
    person.answer = "confirm"
    created = await propose_esun(s)
    await s.call("ask_to_confirm", project_id=created["project_id"])
    card = await s.call(
        "score_variant",
        variant_id=(await s.call("build_variant", code=PLATE))["variant_id"],
        material_key="esun-pla-silk",
        brief_id=created["brief_id"],
    )
    assert card["material"]["key"] == "project-esun-pla-silk"
    assert card["material"]["set_by"]["statement"] == "Made of esun-pla-silk"


ACME = "acme-matte-pla"
QUOTE = "Density 1.10 g/cm3"


def table_with_acme(tmp_path: Path) -> Path:
    document = yaml.safe_load(TABLE_PATH.read_bytes())
    row = next(row for row in document["materials"] if row["key"] == "prusament-pla")
    document["materials"].append({**row, "key": ACME, "name": "Acme Matte PLA"})
    path = tmp_path / "materials.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True))
    return path


@pytest.mark.docker
async def test_a_git_row_added_after_research_grades_on_git_values(
    s: Session, person: Person, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    person.answer = "confirm"
    created = await s.call("create_brief", text="A plate in Acme Matte PLA under 150 g")
    await s.call(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[made_of(ACME, "Acme Matte PLA"), UNDER_150],
    )
    await s.call("ask_to_confirm", project_id=created["project_id"])
    project = briefs.read_brief(s.roots, created["brief_id"]).project
    question = Question(
        created["brief_id"], project, f"project-{ACME}", "density", 1.1, "g/cm3", URL, QUOTE
    )
    page = Page(URL, "Acme data", f"Physical properties {QUOTE}", "ab" * 32)
    assert isinstance(
        submit(load_materials(), s.roots.projects, question, fetcher=lambda _: page),
        ResearchAccepted,
    )

    monkeypatch.setattr(load_materials, "__defaults__", (table_with_acme(tmp_path),))
    variant_id = (await s.call("build_variant", code=PLATE))["variant_id"]
    for key in (f"project-{ACME}", ACME):
        card = await s.call(
            "score_variant", variant_id=variant_id, material_key=key, brief_id=created["brief_id"]
        )
        assert card["material"]["key"] == ACME
        assert card["material"]["set_by"]["statement"] == (
            f"Made of {ACME}. The materials table had no {ACME} when the person confirmed this; "
            "it has one now, so the checks read the table's values, not researched ones."
        )
        mass = next(r for r in card["results"] if r["check_id"] == "mass")
        assert mass["reads"] == [{"kind": "cited", "field": "density"}]
        [judged] = card["basis"]["requirements"]
        assert judged["basis"] == "checks"
