from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from cad.context_parts.store import confirmed_parts, part_brep, stored_parts, variant_of
from cad.projects.model import ProjectId, TamperedProject

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = pytest.mark.anyio
TEXT = "A clip that slides onto the rail, at least 0.2 mm clear of it"


async def brief(s: Session) -> dict[str, Any]:
    return await s.call("create_brief", text=TEXT)


def records(s: Session, project: str) -> list[Path]:
    return sorted((s.roots.projects / project / "context_parts").glob("*.signed"))


def rail(s: Session, created: dict[str, Any], **changed: str) -> dict[str, str]:
    return {
        "brief_id": created["brief_id"],
        "quote": "the rail",
        "name": "rail",
        "variant_id": s.variant("result = Box(30, 20, 10)\n"),
        **changed,
    }


async def propose(s: Session, created: dict[str, Any], **changed: str) -> str:
    return await s.text("propose_context_part", **rail(s, created, **changed))


async def test_proposing_the_same_part_again_returns_the_stored_one(s: Session) -> None:
    created = await brief(s)
    first = await s.call("propose_context_part", **rail(s, created))
    same_shape = s.variant("result = Box(30, 20, 10)  # the same shape\n")
    second = await s.call(
        "propose_context_part",
        **rail(s, created, quote="slides onto the rail", name="again", variant_id=same_shape),
    )
    asked = await s.call("ask_to_confirm", project_id=created["project_id"])
    assert second["part_id"] == first["part_id"]
    assert len(records(s, created["project_id"])) == 1
    assert [i["name"] for i in asked["items"]] == ["rail"]


@pytest.mark.parametrize(
    ("changed", "refusal"),
    [
        ({"quote": "the shelf"}, "BadContextPart: the quote does not appear in brief"),
        ({"variant_id": "0123456789abcdef"}, "UnknownVariant: no variant 0123456789abcdef"),
        ({"variant_id": "../outside"}, "UnknownVariant: a variant id is 16 lowercase hex"),
    ],
)
async def test_a_part_the_store_cannot_place_is_refused(
    s: Session, changed: dict[str, str], refusal: str
) -> None:
    created = await brief(s)
    said = await propose(s, created, **changed)
    assert refusal in said
    assert records(s, created["project_id"]) == []


async def test_an_unbuilt_variant_or_a_shape_that_is_not_a_part_is_refused(s: Session) -> None:
    created = await brief(s)
    unbuilt = await propose(s, created, variant_id=s.variant("raise NameError\n", None))
    no_solid = s.variant("result = Face()\n", s.rows.not_a_part)
    not_a_part = await propose(s, created, variant_id=no_solid)
    assert "NotBuilt: variant" in unbuilt
    assert f"BadContextPart: variant {no_solid} cannot be a context part: it has no solid" in (
        not_a_part
    )
    assert records(s, created["project_id"]) == []
    assert not (s.roots.projects / created["project_id"] / "parts").exists()


async def test_a_tampered_or_unsigned_record_is_refused(s: Session) -> None:
    created = await brief(s)
    await propose(s, created)
    project = created["project_id"]
    [stored] = records(s, project)
    original = stored.read_bytes()
    stored.write_bytes(original.replace(b'"rail"', b'"bolt"'))
    tampered = await s.text("ask_to_confirm", project_id=project)
    with pytest.raises(TamperedProject):
        stored_parts(s.roots.projects, ProjectId(project))
    stored.write_bytes(original)
    (stored.parent / "0002.signed").write_bytes(original.partition(b"\n")[2])
    unsigned = await propose(s, created, variant_id=s.variant("result = Box(1, 1, 1)\n", b"x"))
    assert "TamperedProject: project" in tampered
    assert "has a context part this store did not sign" in unsigned
    assert len(records(s, project)) == 2


async def test_a_part_whose_geometry_changed_on_disk_is_refused(s: Session) -> None:
    created = await brief(s)
    await propose(s, created)
    project = ProjectId(created["project_id"])
    await s.call("ask_to_confirm", project_id=project)
    s.post(s.person.url, "confirm")
    [part] = confirmed_parts(s.roots.projects, project)
    [brep] = (s.roots.projects / project / "parts").glob("*.brep")
    brep.write_bytes(s.rows.rail + b"moved")
    with pytest.raises(TamperedProject, match="has lost its geometry"):
        part_brep(s.roots.projects, part)
    brep.unlink()
    source = variant_of(part.record)
    assert source is not None
    brep.symlink_to(s.variants / source / "result.brep")
    with pytest.raises(TamperedProject):
        part_brep(s.roots.projects, part)


def clear_of(part: str) -> dict[str, Any]:
    return {
        "target": {
            "kind": "min_clearance",
            "part": part,
            "clearance": {"magnitude": 0.2, "unit": "mm"},
        },
        "quote": "at least 0.2 mm clear of it",
    }


async def test_a_clearance_names_only_a_part_its_project_stores(s: Session) -> None:
    created = await brief(s)
    refused = await s.text(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[clear_of("part-" + "0" * 16)],
    )
    assert "is not a context part of this brief's project" in refused
    part = await s.call("propose_context_part", **rail(s, created))
    proposed = await s.call(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[clear_of(part["part_id"])],
    )
    (row,) = proposed["requirements"]
    assert (row["check"], row["plain"]) == (
        "fit",
        f"At least 0.2 mm clear of context part {part['part_id']}",
    )


async def test_the_part_brep_is_stored_once_with_no_temporary(s: Session) -> None:
    created = await brief(s)
    await propose(s, created)
    parts = s.roots.projects / created["project_id"] / "parts"
    [brep] = parts.iterdir()
    assert brep.name == f"{hashlib.sha256(brep.read_bytes()).hexdigest()}.brep"


async def test_an_unwritable_parts_directory_fails_the_proposal_and_leaves_no_temporary(
    s: Session,
) -> None:
    created = await brief(s)
    parts = s.roots.projects / created["project_id"] / "parts"
    parts.mkdir(parents=True)
    parts.chmod(0o555)
    try:
        failed = await propose(s, created)
    finally:
        parts.chmod(0o755)
    assert "Error executing tool propose_context_part" in failed
    assert list(parts.iterdir()) == []
    assert records(s, created["project_id"]) == []
