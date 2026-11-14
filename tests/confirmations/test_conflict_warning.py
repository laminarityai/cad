from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any, Final

import pytest

from cad.research.fetch import Page
from cad.research.submit import Question, ResearchAccepted, submit
from cad.tables.materials import load_materials
from tests.support.cube import CUBE, CUBE_TEXT, PLA, min_mass

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = pytest.mark.anyio
WARNING: Final = "Warning: these requirements conflict"
NOT_CHECKED: Final = "Not checked yet: the mass and the size"


async def brief(s: Session, *requirements: dict[str, Any], project_id: str | None = None) -> str:
    joined = {} if project_id is None else {"project_id": project_id}
    created = await s.call("create_brief", text=CUBE_TEXT, **joined)
    await propose(s, created["brief_id"], *requirements)
    return created["project_id"]


async def propose(s: Session, brief_id: str, *requirements: dict[str, Any]) -> None:
    await s.call("propose_requirements", brief_id=brief_id, requirements=list(requirements))


async def page(s: Session, project_id: str) -> str:
    await s.call("ask_to_confirm", project_id=project_id)
    status, body = s.get(s.person.url)
    assert status == 200
    return body


async def test_a_cube_that_cannot_weigh_50_g_is_warned_of_with_the_bound(s: Session) -> None:
    body = await page(s, await brief(s, CUBE, PLA, min_mass(50)))
    assert body.count(WARNING) == 1
    assert "The mass must be at least 50 g, but Prusament PLA at 1.24 g/cm³ weighs 9.92 g" in body
    for quote in ("fits in a 20 mm cube", "PLA", "at least 50 g"):
        assert f'<q class="origin">{html.escape(quote)}</q>' in body


async def test_the_warning_holds_no_control_and_the_page_still_answers(s: Session) -> None:
    body = await page(s, await brief(s, CUBE, PLA, min_mass(50)))
    warning = body[body.index('<div class="warning"') : body.index("</div>", body.index(WARNING))]
    assert "<button" not in warning
    assert "<input" not in warning
    assert "<textarea" not in warning
    assert '<button name="answer" value="confirm">Confirm</button>' in body


async def test_a_brief_with_no_conflict_shows_no_warning(s: Session) -> None:
    body = await page(s, await brief(s, CUBE, PLA, min_mass(5)))
    assert WARNING not in body
    assert 'class="warning"' not in body


async def test_a_proposal_that_adds_to_the_confirmed_set_is_warned_of_a_conflict_with_it(
    s: Session,
) -> None:
    created = await s.call("create_brief", text=CUBE_TEXT)
    await propose(s, created["brief_id"], CUBE, PLA)
    s.person.answer = "confirm"
    await s.call("ask_to_confirm", project_id=created["project_id"])
    s.person.answer = None
    await propose(s, created["brief_id"], min_mass(50))
    body = await page(s, created["project_id"])
    assert body.count(WARNING) == 1
    assert "weighs 9.92 g filling the whole 20 x 20 x 20 mm box" in body


async def test_a_proposal_that_repeats_the_confirmed_set_with_a_conflict_is_warned_of(
    s: Session,
) -> None:
    created = await s.call("create_brief", text=CUBE_TEXT)
    await propose(s, created["brief_id"], CUBE, PLA)
    s.person.answer = "confirm"
    await s.call("ask_to_confirm", project_id=created["project_id"])
    s.person.answer = None
    await propose(s, created["brief_id"], CUBE, PLA, min_mass(50))
    body = await page(s, created["project_id"])
    assert body.count(WARNING) == 1
    assert "weighs 9.92 g filling the whole 20 x 20 x 20 mm box" in body


async def test_a_material_with_no_density_yet_says_the_mass_is_not_checked(s: Session) -> None:
    unknown = {"target": {"kind": "made_of", "material": "no-such-material"}, "quote": "PLA"}
    body = await page(s, await brief(s, CUBE, unknown, min_mass(50)))
    assert WARNING not in body
    assert body.count(NOT_CHECKED) == 1
    assert "no-such-material has no density yet" in body
    assert "is not checked until its density is researched" in body
    for quote in ("fits in a 20 mm cube", "PLA", "at least 50 g"):
        assert f'<q class="origin">{html.escape(quote)}</q>' in body


async def test_a_researched_density_turns_the_note_into_a_warning(s: Session) -> None:
    unknown = {"target": {"kind": "made_of", "material": "no-such-material"}, "quote": "PLA"}
    created = await s.call("create_brief", text=CUBE_TEXT)
    brief_id, project_id = created["brief_id"], created["project_id"]
    await propose(s, brief_id, CUBE, unknown, min_mass(50))
    url, quote = "https://example.org/no-such-material", "Density 1.10 g/cm3"
    question = Question(
        brief_id, project_id, "project-no-such-material", "density", 1.1, "g/cm3", url, quote
    )
    page_read = Page(url, "Data", f"Physical properties {quote}", "ab" * 32)
    fetched = submit(load_materials(), s.roots.projects, question, fetcher=lambda _: page_read)
    assert isinstance(fetched, ResearchAccepted)
    body = await page(s, project_id)
    assert NOT_CHECKED not in body
    assert body.count(WARNING) == 1
    assert "weighs 8.8 g filling the whole 20 x 20 x 20 mm box" in body


async def test_a_known_density_shows_no_not_checked_note(s: Session) -> None:
    body = await page(s, await brief(s, CUBE, PLA, min_mass(5)))
    assert NOT_CHECKED not in body


async def test_an_unknown_material_still_warns_of_a_conflict_that_needs_no_density(
    s: Session,
) -> None:
    unknown = {"target": {"kind": "made_of", "material": "no-such-material"}, "quote": "PLA"}
    heavy = {
        "target": {
            "kind": "measure_limit",
            "check_id": "mass",
            "measure": "volume",
            "comparator": "at_least",
            "limit": {"magnitude": 9, "unit": "cm^3"},
        },
        "quote": "at least 50 g",
    }
    body = await page(s, await brief(s, CUBE, unknown, heavy))
    assert body.count(WARNING) == 1
    assert (
        "The volume of material in the part must be at least 9 cm³, but the whole "
        "20 x 20 x 20 mm box holds 8 cm³"
    ) in body


async def test_another_projects_page_carries_no_warning(s: Session) -> None:
    await brief(s, CUBE, PLA, min_mass(50))
    other = await s.call("create_brief", text="A wall hook, under 150 g")
    await propose(
        s,
        other["brief_id"],
        {
            "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
            "quote": "under 150 g",
        },
    )
    body = await page(s, other["project_id"])
    assert WARNING not in body


async def test_two_conflicts_in_one_brief_are_two_warnings(s: Session) -> None:
    volume = {
        "target": {
            "kind": "measure_limit",
            "check_id": "mass",
            "measure": "volume",
            "comparator": "at_least",
            "limit": {"magnitude": 9, "unit": "cm^3"},
        },
        "quote": "at least 50 g",
    }
    body = await page(s, await brief(s, CUBE, PLA, min_mass(50), volume))
    assert body.count(WARNING) == 2
