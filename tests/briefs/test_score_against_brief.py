from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from cad.checks import job_store

if TYPE_CHECKING:
    from tests.support.browser import Person
    from tests.support.session import Session

pytestmark = pytest.mark.anyio

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
PLATE_TEXT = "A plate under 150 g, at least 50 g, fits in 120 x 80 x 40 mm, looks friendly"
ROWS: list[dict[str, Any]] = [
    {
        "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
        "quote": "under 150 g",
    },
    {
        "target": {"kind": "min_mass", "mass": {"magnitude": 50, "unit": "g"}},
        "quote": "at least 50 g",
    },
    {
        "target": {
            "kind": "envelope",
            "edges": [{"magnitude": edge, "unit": "mm"} for edge in (120, 80, 40)],
        },
        "quote": "fits in 120 x 80 x 40 mm",
    },
    {"target": {"kind": "unchecked", "statement": "looks friendly"}, "quote": "looks friendly"},
]


async def plate(s: Session) -> str:
    return (await s.call("build_variant", code=PLATE))["variant_id"]


async def proposed(s: Session) -> tuple[str, str]:
    created = await s.call("create_brief", text=PLATE_TEXT)
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=ROWS)
    return created["brief_id"], created["project_id"]


def jobs_path(s: Session, variant_id: str) -> Path:
    return s.roots.briefs.parent / "variants" / variant_id / job_store.JOBS


async def test_a_score_with_no_brief_says_so_and_judges_nothing(s: Session) -> None:
    card = await s.call("score_variant", variant_id=await plate(s), material_key="prusament-pla")
    assert card["basis"] == {"kind": "no_brief"}


async def test_a_brief_nobody_confirmed_runs_every_check_and_judges_nothing(s: Session) -> None:
    brief_id, _ = await proposed(s)
    card = await s.call(
        "score_variant", variant_id=await plate(s), material_key="prusament-pla", brief_id=brief_id
    )
    assert card["basis"] == {"kind": "awaiting_confirmation", "brief_id": brief_id}
    assert [r["verdict"] for r in card["results"]] == ["pass"] * 4


async def test_a_confirmed_brief_is_judged_requirement_by_requirement(
    s: Session, person: Person
) -> None:
    person.answer = "confirm"
    brief_id, project_id = await proposed(s)
    assert (await s.call("ask_to_confirm", project_id=project_id))["status"] == "answered"
    variant_id = await plate(s)
    card = await s.call(
        "score_variant", variant_id=variant_id, material_key="prusament-pla", brief_id=brief_id
    )
    basis = card["basis"]
    assert basis["kind"] == "against_brief"
    assert basis["brief_id"] == brief_id
    judged = [(r["kind"], r.get("check_id"), r.get("verdict")) for r in basis["requirements"]]
    assert judged == [
        ("checked", "mass", "pass"),
        ("checked", "mass", "fail"),
        ("checked", "extents", "pass"),
        ("unverified", None, None),
    ]
    assert basis["unverified_requirements"] == [basis["requirements"][3]["requirement_id"]]
    assert basis["requirements"][0]["comparisons"] == [
        {
            "measure": "mass",
            "comparator": "at_most",
            "limit": {"magnitude": 150.0, "unit": "g"},
            "verdict": "pass",
        }
    ]
    assert jobs_path(s, variant_id).is_dir()


@pytest.mark.parametrize(
    ("brief_id", "refusal"),
    [("0123456789abcdef", "UnknownBrief"), ("../etc", "UnknownBrief")],
)
async def test_a_brief_the_store_cannot_show_is_refused_before_any_check_runs(
    s: Session, brief_id: str, refusal: str
) -> None:
    variant_id = await plate(s)
    text = await s.text(
        "score_variant", variant_id=variant_id, material_key="prusament-pla", brief_id=brief_id
    )
    assert refusal in text
    assert not jobs_path(s, variant_id).exists()


async def test_a_tampered_brief_is_refused_before_any_check_runs(s: Session) -> None:
    brief_id, _ = await proposed(s)
    (s.roots.briefs / brief_id / "decisions" / "0001.signed").write_text('{"verdict":"confirmed"}')
    variant_id = await plate(s)
    text = await s.text(
        "score_variant", variant_id=variant_id, material_key="prusament-pla", brief_id=brief_id
    )
    assert "TamperedBrief" in text
    assert not jobs_path(s, variant_id).exists()
