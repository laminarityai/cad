from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cad.checks import job_store
from tests.support.loaded_plate import LOAD, PLATE_TEXT, plate, settled

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.browser import Person
    from tests.support.session import Session

pytestmark = [pytest.mark.anyio, pytest.mark.docker]


def jobs_path(s: Session, variant_id: str) -> Path:
    return s.roots.briefs.parent / "variants" / variant_id / job_store.JOBS


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
