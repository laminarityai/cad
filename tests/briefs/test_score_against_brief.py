from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from cad.checks import job_store

if TYPE_CHECKING:
    from tests.support.browser import Person
    from tests.support.session import Session

pytestmark = [pytest.mark.anyio, pytest.mark.docker]

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
LOAD: dict[str, Any] = {
    "support": {"kind": "flat_end"},
    "load": {
        "kind": "far_end",
        "force": {"magnitude": 10, "unit": "N"},
        "direction": {"kind": "any"},
    },
}


async def plate(s: Session) -> str:
    return (await s.call("build_variant", code=PLATE))["variant_id"]


async def proposed(s: Session) -> tuple[str, str]:
    created = await s.call("create_brief", text=PLATE_TEXT)
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=ROWS)
    return created["brief_id"], created["project_id"]


async def settled(s: Session, **score: str) -> dict[str, Any]:
    card = await s.call("score_variant", **score)
    for _ in range(40):
        if not card["pending"]:
            return card
        card = await s.call("score_variant", **score)
    raise AssertionError(f"still pending: {card['pending']}")


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
    assert [r["verdict"] for r in card["results"]] == ["pass"] * 5


async def test_a_target_that_waits_shows_its_measure_beside_it_and_no_verdict(s: Session) -> None:
    brief_id, _ = await proposed(s)
    card = await s.call(
        "score_variant", variant_id=await plate(s), material_key="prusament-pla", brief_id=brief_id
    )
    rows = card["awaiting"]
    assert [row["check_id"] for row in rows] == ["mass", "mass", "extents"]
    assert all(row["label"] == "waiting for your Confirm, no verdict" for row in rows)
    assert not {"verdict", "comparisons", "mark"} & set(rows[0])
    [value] = rows[0]["values"]
    assert value["proposed"] == {"magnitude": 150.0, "unit": "g"}
    assert value["measured"] is not None
    assert "requirements" not in card["basis"]


async def test_fea_is_asked_for_a_load_that_awaits_confirm_and_for_an_assumed_one(
    s: Session,
) -> None:
    created = await s.call("create_brief", text=f"{PLATE_TEXT}, holds 10 N")
    load = LOAD
    row = {
        "target": {"kind": "min_safety_factor", "load": load, "factor": 2},
        "quote": "holds 10 N",
    }
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=[row])
    card = await settled(
        s, variant_id=await plate(s), material_key="prusament-pla", brief_id=created["brief_id"]
    )
    asked = [one["instance"] for one in card["results"] if one["check_id"] == "fea"]
    assert len(asked) == 1 and asked[0] != ""
    assert [row["instance"] for row in card["awaiting"]] == asked
    [fea] = [one for one in card["results"] if one["check_id"] == "fea"]
    assert fea["kind"] == "measure_only" and "verdict" not in fea
    assert all("verdict" in one for one in card["results"] if one["check_id"] != "fea")
    other = {**load, "load": {**load["load"], "force": {"magnitude": 20, "unit": "N"}}}
    mine = {
        "target": {
            "kind": "max_deflection",
            "load": other,
            "deflection": {"magnitude": 1, "unit": "mm"},
        },
        "why": "a desk shelf",
    }
    await s.call("propose_requirements", brief_id=created["brief_id"], assumptions=[mine])
    again = await settled(
        s, variant_id=await plate(s), material_key="prusament-pla", brief_id=created["brief_id"]
    )
    loads = {one["instance"] for one in again["results"] if one["check_id"] == "fea"}
    assert len(loads) == 2
    assert {row["instance"] for row in again["assumptions"]} <= loads
    assert all(
        one["kind"] == "measure_only" for one in again["results"] if one["check_id"] == "fea"
    )


async def test_a_load_judged_after_confirm_reads_the_stored_result_with_no_rebuild(
    s: Session, person: Person
) -> None:
    created = await s.call("create_brief", text=f"{PLATE_TEXT}, holds 10 N")
    row = {
        "target": {"kind": "min_safety_factor", "load": LOAD, "factor": 2},
        "quote": "holds 10 N",
    }
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=[row])
    variant_id = await plate(s)
    score = {"variant_id": variant_id, "material_key": "prusament-pla"}
    waiting = await settled(s, **score, brief_id=created["brief_id"])
    [measured] = [one for one in waiting["results"] if one["check_id"] == "fea"]
    assert measured["kind"] == "measure_only" and "verdict" not in measured
    ran = sorted(jobs_path(s, variant_id).iterdir())
    person.answer = "confirm"
    await s.call("ask_to_confirm", project_id=created["project_id"])
    judged = await s.call("score_variant", **score, brief_id=created["brief_id"])
    assert sorted(jobs_path(s, variant_id).iterdir()) == ran
    [fea] = [one for one in judged["results"] if one["check_id"] == "fea"]
    assert "kind" not in fea and fea["verdict"] in {"pass", "unknown"}
    assert {k: v for k, v in fea.items() if k != "verdict"} == {
        k: v for k, v in measured.items() if k not in {"kind", "label"}
    }
    [decided] = judged["basis"]["requirements"]
    assert decided["check_id"] == "fea" and "verdict" in decided


async def test_confirming_judges_the_stored_results_with_no_rebuild(
    s: Session, person: Person
) -> None:
    brief_id, project_id = await proposed(s)
    variant_id = await plate(s)
    score = {"variant_id": variant_id, "material_key": "prusament-pla", "brief_id": brief_id}
    waiting = await s.call("score_variant", **score)
    ran = sorted(jobs_path(s, variant_id).iterdir())
    person.answer = "confirm"
    assert (await s.call("ask_to_confirm", project_id=project_id))["status"] == "answered"
    judged = await s.call("score_variant", **score)
    assert sorted(jobs_path(s, variant_id).iterdir()) == ran
    assert judged["results"] == waiting["results"]
    assert judged["basis"]["kind"] == "against_brief"
    assert "awaiting" not in judged


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
