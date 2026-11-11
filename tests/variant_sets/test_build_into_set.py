from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cad.sandbox.image import BUILD, image_tag
from cad.variant_sets import store
from cad.variant_sets.model import MAX_MEMBERS
from cad.variants import entry
from cad.variants.entry import VariantId
from tests.support.set_parts import BRACKET, NO_DOCKER, PLATE, held, shows

if TYPE_CHECKING:
    from tests.support.variant_set_session import Session

pytestmark = pytest.mark.anyio


async def test_a_member_survives_a_trust_digest_change(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed_brief()
    before = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    monkeypatch.setattr(entry, "TRUST_DIGEST", "a server version from a later deploy")
    [member] = held(s, brief_id)
    live = member.latest.live_id(image_tag(BUILD))
    assert member.latest.built_as == before["variant_id"] != live
    after = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    assert after["variant_id"] == live
    assert after["variant_set"] == {
        "kind": "joined",
        "slot": 1,
        "revision": 1,
        "limit": MAX_MEMBERS,
        "already_member": True,
    }
    assert shows(s, brief_id) == [before["variant_id"]]


async def test_building_a_member_again_keeps_its_slot_and_starts_no_container(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed_brief()
    first = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    assert first["variant_set"]["slot"] == 1
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    again = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    assert again["variant_id"] == first["variant_id"]
    assert (again["variant_set"]["slot"], again["variant_set"]["already_member"]) == (1, True)


async def test_a_brief_nobody_confirmed_still_builds_into_its_set(s: Session) -> None:
    brief_id = await s.proposed_brief()
    built = await s.call(
        "build_variant",
        code=PLATE,
        brief_id=brief_id,
        material_key="prusament-pla",
        material_reason="light",
    )
    assert built["variant_set"] == {
        "kind": "joined",
        "slot": 1,
        "revision": 1,
        "limit": MAX_MEMBERS,
        "already_member": False,
    }
    assert shows(s, brief_id) == [built["variant_id"]]


async def test_a_full_set_refuses_new_code_before_any_container(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed_brief()
    key = store.set_key(s.roots, brief_id)
    for number in range(MAX_MEMBERS):
        store.join(s.tmp / "projects", key, f"code {number}", VariantId("0" * 16))
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id)
    assert f"SetFull: the variant set of brief {brief_id} holds 5 variants, its limit" in text


async def test_confirming_editing_or_declining_later_keeps_the_options_in_the_set(
    s: Session,
) -> None:
    brief_id = await s.proposed_brief()
    first = await s.call(
        "build_variant",
        code=PLATE,
        brief_id=brief_id,
        material_key="prusament-pla",
        material_reason="light",
    )
    await s.confirm(brief_id)
    second = await s.call("build_variant", code=BRACKET, brief_id=brief_id)
    assert second["variant_set"]["slot"] == 2
    await s.call(
        "propose_requirements",
        brief_id=brief_id,
        requirements=[
            {"target": {"kind": "made_of", "material": "prusament-pla"}, "quote": "PLA"},
            {"target": {"kind": "closed_solid"}, "quote": "A plate"},
        ],
    )
    await s.confirm(brief_id)
    again = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    assert again["variant_set"]["slot"] == 1
    assert shows(s, brief_id) == [first["variant_id"], second["variant_id"]]


async def test_a_build_that_fails_joins_no_set(s: Session) -> None:
    brief_id = await s.confirmed_brief()
    failed = await s.call("build_variant", code="x = 1\n", brief_id=brief_id)
    assert failed["outcome"]["kind"] == "no_result"
    assert failed["variant_set"]["kind"] == "not_joined"
    assert held(s, brief_id) == []


async def test_a_build_with_no_brief_joins_no_set(s: Session) -> None:
    built = await s.call("build_variant", code=PLATE)
    assert built["outcome"] == {"kind": "built"}
    assert built["variant_set"] is None
    assert not (s.tmp / "projects").exists()


async def test_a_plain_build_then_a_set_build_joins_from_the_cache(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed_brief()
    plain = await s.call("build_variant", code=PLATE)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    joined = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    assert joined["variant_id"] == plain["variant_id"]
    assert joined["variant_set"] == {
        "kind": "joined",
        "slot": 1,
        "revision": 1,
        "limit": MAX_MEMBERS,
        "already_member": False,
    }
    assert shows(s, brief_id) == [plain["variant_id"]]


async def test_oversized_code_is_refused_before_any_container(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed_brief()
    monkeypatch.setattr(store, "MAX_MEMBER_BYTES", 10)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id)
    assert "SetRefused: this code is too large" in text
    assert held(s, brief_id) == []


async def test_two_briefs_confirmed_by_one_answer_each_build_into_their_own_set(
    s: Session,
) -> None:
    first = await s.proposed_brief()
    project_id = (await s.call("list_requirements", brief_id=first))["project_id"]
    second = await s.proposed_brief(project_id)
    await s.confirm(first)
    for brief_id in (first, second):
        built = await s.call("build_variant", code=PLATE, brief_id=brief_id)
        assert built["variant_set"] == {
            "kind": "joined",
            "slot": 1,
            "revision": 1,
            "limit": MAX_MEMBERS,
            "already_member": False,
        }
        assert shows(s, brief_id) == [built["variant_id"]]
