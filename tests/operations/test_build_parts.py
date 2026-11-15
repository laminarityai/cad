"""A build reads and places the supplied parts of its brief's project, and the rules on which it
may place (ADR-0012). The sandbox is faked: tests/sandbox/test_build_parts.py runs it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from cad.accounts.principal import AccountId, PersonSession
from cad.context_parts.ids import ContextPartId
from cad.projects.model import ProjectId
from cad.sandbox import builder, image
from cad.sandbox.builder import Artifacts, Run, Supplied
from cad.sandbox.outcome import Built
from cad.uploads import store
from cad.uploads.model import kind_of
from tests.support.rows import RAIL, fake_ingest

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tests.support.session import Session

pytestmark = pytest.mark.anyio
PLATE = "result = Box(100, 60, 5)\n"
SHAPE = b"CASCADE Topology V3, a plate\n"
SPOT = {"at": [30.0, 20.0, 0.0], "rotate": [0.0, 0.0, 90.0]}
CHOSEN = {"material_key": "prusament-pla", "material_reason": "light"}
PERSON = PersonSession(account=AccountId("user_alice"), session_id="sess_1")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Sequence[Supplied]]:
    """The parts each build was sent."""
    builds: list[Sequence[Supplied]] = []

    def build(
        code: str, image_id: str, *, wall_seconds: int, parts: Sequence[Supplied] = ()
    ) -> Run:
        builds.append(parts)
        return Run(Artifacts(SHAPE, Built()), "")

    monkeypatch.setattr(builder, "build", build)
    monkeypatch.setattr(image, "current_image", "sha256:{}".format)
    return builds


async def project_with_part(s: Session) -> tuple[str, str, str]:
    created = await s.call("create_brief", text=s.rows.text)
    at, kind = ProjectId(created["project_id"]), kind_of("wheel.step")
    part = store.add_part(s.roots.projects, at, "wheel.step", kind, None, RAIL, PERSON, fake_ingest)
    return created["project_id"], created["brief_id"], part.record.id


def placing(part: str, *spots: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"part_id": part, "placements": list(spots)}]


async def test_a_build_is_sent_the_confirmed_part_and_records_where_it_placed_it(
    s: Session, sent: list[Sequence[Supplied]]
) -> None:
    project, brief, part = await project_with_part(s)
    built = await s.call(
        "build_variant", code=PLATE, brief_id=brief, parts=placing(part, SPOT), **CHOSEN
    )
    [[wheel]] = sent
    assert (wheel.brep, wheel.use.part_id, wheel.use.project) == (RAIL, part, project)
    assert [p.model_dump(mode="json") for p in wheel.use.placements] == [SPOT]
    code = await s.call("variant_code", variant_id=built["variant_id"])
    assert code["parts"] == placing(part, SPOT)
    again = await s.call(
        "build_variant", code=PLATE, brief_id=brief, parts=placing(part, SPOT), **CHOSEN
    )
    assert (again["variant_id"], again["variant_set"]["already_member"]) == (
        built["variant_id"],
        True,
    )
    assert len(sent) == 1


async def test_the_same_code_placing_a_part_elsewhere_is_another_variant(
    s: Session, sent: list[Sequence[Supplied]]
) -> None:
    _, brief, part = await project_with_part(s)
    first = await s.call(
        "build_variant", code=PLATE, brief_id=brief, parts=placing(part, SPOT), **CHOSEN
    )
    moved = {"at": [-30.0, 20.0, 0.0], "rotate": [0.0, 0.0, 0.0]}
    second = await s.call(
        "build_variant", code=PLATE, brief_id=brief, parts=placing(part, moved), **CHOSEN
    )
    plain = await s.call("build_variant", code=PLATE, brief_id=brief, **CHOSEN)
    assert len({first["variant_id"], second["variant_id"], plain["variant_id"]}) == 3
    slots = [one["variant_set"]["slot"] for one in (first, second, plain)]
    assert slots == [1, 2, 3]


async def test_parts_without_a_brief_are_refused_and_nothing_is_built(
    s: Session, sent: list[Sequence[Supplied]]
) -> None:
    _, _, part = await project_with_part(s)
    said = await s.text("build_variant", code=PLATE, parts=placing(part, SPOT))
    assert "pass brief_id too" in said
    assert sent == []


async def test_a_part_of_another_project_is_refused(
    s: Session, sent: list[Sequence[Supplied]]
) -> None:
    _, _, part = await project_with_part(s)
    other = await s.call("create_brief", text=s.rows.text)
    said = await s.text(
        "build_variant", code=PLATE, brief_id=other["brief_id"], parts=placing(part), **CHOSEN
    )
    assert f"{part} is not a confirmed part of project {other['project_id']}" in said
    assert sent == []


async def test_a_part_named_twice_is_refused(s: Session, sent: list[Sequence[Supplied]]) -> None:
    _, brief, part = await project_with_part(s)
    twice = [*placing(part, SPOT), *placing(part)]
    said = await s.text("build_variant", code=PLATE, brief_id=brief, parts=twice, **CHOSEN)
    assert "names a part twice" in said
    assert sent == []


async def fits_with(s: Session, brief: str, part: str) -> None:
    target = {"kind": "fits_with", "part": part}
    await s.call(
        "propose_requirements",
        brief_id=brief,
        requirements=[{"target": target, "quote": "fits in 120 x 80 x 40 mm"}],
    )


async def test_a_build_may_read_a_part_its_brief_must_fit_but_not_place_it(
    s: Session, sent: list[Sequence[Supplied]]
) -> None:
    _, brief, part = await project_with_part(s)
    await fits_with(s, brief, part)
    said = await s.text(
        "build_variant", code=PLATE, brief_id=brief, parts=placing(part, SPOT), **CHOSEN
    )
    assert f"{part} is a part brief {brief} must fit" in said
    assert sent == []
    read = await s.call("build_variant", code=PLATE, brief_id=brief, parts=placing(part), **CHOSEN)
    assert read["outcome"]["kind"] == "built"
    assert [one.use.placements for one in sent[0]] == [()]


async def test_scoring_refuses_a_variant_that_placed_a_part_its_brief_now_must_fit(
    s: Session, sent: list[Sequence[Supplied]]
) -> None:
    _, brief, part = await project_with_part(s)
    built = await s.call(
        "build_variant", code=PLATE, brief_id=brief, parts=placing(part, SPOT), **CHOSEN
    )
    await fits_with(s, brief, part)
    said = await s.text("score_variant", variant_id=built["variant_id"], brief_id=brief)
    assert f"places {part}, which the brief's fit check now measures" in said


async def test_scoring_refuses_a_variant_whose_parts_the_briefs_project_has_not_confirmed(
    s: Session, sent: list[Sequence[Supplied]]
) -> None:
    project, brief, part = await project_with_part(s)
    built = await s.call(
        "build_variant", code=PLATE, brief_id=brief, parts=placing(part, SPOT), **CHOSEN
    )
    vid = built["variant_id"]
    other = await s.call("create_brief", text=s.rows.text)
    said = await s.text(
        "score_variant", variant_id=vid, brief_id=other["brief_id"], material_key="prusament-pla"
    )
    assert f"variant {vid} read {part}, which the brief's project has not confirmed" in said
    said = await s.text("score_variant", variant_id=vid, material_key="prusament-pla")
    assert f"variant {vid} read supplied parts, so pass brief_id too" in said
    store.decline_part(
        s.roots.projects, ProjectId(project), ContextPartId(part), "not this wheel", PERSON
    )
    said = await s.text("scorecard", variant_id=vid, brief_id=brief)
    assert f"variant {vid} read {part}, which the brief's project has not confirmed" in said
