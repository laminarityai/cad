from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

if TYPE_CHECKING:
    from tests.support.variant_set_session import Session

pytestmark = pytest.mark.anyio

PLATE: Final = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
THICKER: Final = PLATE + "\n# a thicker wall\n"
NO_DOCKER: Final = "unix:///nonexistent/docker.sock"
UNDER_150: Final = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}
PLA: Final = {"material_key": "prusament-pla", "material_reason": "PLA is light"}
FLAT: Final = {"label": "Flat plate", "differs": "Thinnest and lightest of the set"}
RIBBED: Final = {"label": "Ribbed plate", "differs": "Ribs underneath make it the stiffest"}


async def confirmed(s: Session) -> tuple[str, str]:
    brief_id = await s.proposed_brief(None, "A plate under 150 g", UNDER_150)
    await s.confirm(brief_id)
    return (await s.call("list_requirements", brief_id=brief_id))["project_id"], brief_id


async def options(s: Session, project_id: str, brief_id: str) -> list[Any]:
    shown = await s.call("variant_set", project_id=project_id, brief_id=brief_id)
    return [(one["revision"], one["option"]) for one in shown["members"]]


async def test_a_slots_option_shows_in_the_set_and_a_revision_keeps_it(s: Session) -> None:
    project, brief_id = await confirmed(s)
    await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA, **FLAT)
    await s.call("build_variant", code=THICKER, brief_id=brief_id, slot=1)
    assert await options(s, project, brief_id) == [(2, FLAT)]


async def test_a_new_option_on_the_same_code_is_a_new_revision(s: Session) -> None:
    project, brief_id = await confirmed(s)
    await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA, **FLAT)
    same = await s.call("build_variant", code=PLATE, brief_id=brief_id, **FLAT)
    renamed = await s.call("build_variant", code=PLATE, brief_id=brief_id, **RIBBED)
    assert same["variant_set"]["already_member"] is True
    assert (renamed["variant_set"]["revision"], renamed["variant_set"]["already_member"]) == (
        2,
        False,
    )
    assert await options(s, project, brief_id) == [(2, RIBBED)]


async def test_a_label_without_differs_or_without_a_brief_is_refused_before_any_build(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, brief_id = await confirmed(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    alone = await s.refusal(
        "build_variant", code=PLATE, brief_id=brief_id, label=FLAT["label"], **PLA
    )
    unset = await s.refusal("build_variant", code=PLATE, **FLAT)
    assert "label and differs go together" in alone
    assert "pass brief_id too" in unset
    assert await options(s, project, brief_id) == []
