from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cad.sandbox.image import BUILD, image_tag
from cad.variant_sets import store
from cad.variant_sets.model import MAX_MEMBERS
from cad.variants import entry
from cad.variants.entry import VariantId

if TYPE_CHECKING:
    from variant_sets.conftest import Session

pytestmark = pytest.mark.anyio

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
NO_DOCKER = "unix:///nonexistent/docker.sock"


BRACKET = (Path(__file__).parents[1] / "sandbox/parts/l_bracket.py").read_text()
THICKER = PLATE + "\n# a thicker wall\n"


def held(s: Session, brief_id: str) -> list[store.Member]:
    key = store.confirmed_key(s.roots, brief_id)
    return list(store.members(s.tmp / "projects", key))


def shows(s: Session, brief_id: str) -> list[str]:
    return [m.latest.built_as for m in held(s, brief_id)]


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


async def test_a_brief_nobody_confirmed_is_refused_before_any_container(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.proposed_brief()
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id)
    assert text.startswith(
        f"Error executing tool build_variant: NotConfirmed: brief {brief_id} has no confirmed "
        "requirements"
    )
    assert "ask_to_confirm" in text
    assert str(s.tmp) not in text


async def test_a_full_set_refuses_new_code_before_any_container(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed_brief()
    key = store.confirmed_key(s.roots, brief_id)
    for number in range(MAX_MEMBERS):
        store.join(s.tmp / "projects", key, f"code {number}", VariantId("0" * 16))
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id)
    assert f"SetFull: the variant set of brief {brief_id} holds 5 variants, its limit" in text


async def test_a_new_confirmation_starts_an_empty_set(s: Session) -> None:
    brief_id = await s.confirmed_brief()
    await s.call("build_variant", code=PLATE, brief_id=brief_id)
    await s.call(
        "propose_requirements",
        brief_id=brief_id,
        requirements=[{"target": {"kind": "closed_solid"}, "quote": "A plate"}],
    )
    await s.confirm(brief_id)
    joined = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    assert (joined["variant_set"]["slot"], joined["variant_set"]["already_member"]) == (1, False)


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
    assert store.confirmed_key(s.roots, first).decision_sha256 == (
        store.confirmed_key(s.roots, second).decision_sha256
    )
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


async def test_a_change_to_slot_2_becomes_its_next_revision_and_the_old_one_stays_in_history(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed_brief()
    await s.call("build_variant", code=PLATE, brief_id=brief_id)
    bracket = await s.call("build_variant", code=BRACKET, brief_id=brief_id)
    assert bracket["variant_set"]["slot"] == 2
    changed = await s.call("build_variant", code=THICKER, brief_id=brief_id, slot=2)
    assert changed["outcome"] == {"kind": "built"}
    assert changed["variant_id"] != bracket["variant_id"]
    assert changed["variant_set"] == {
        "kind": "joined",
        "slot": 2,
        "revision": 2,
        "limit": MAX_MEMBERS,
        "already_member": False,
    }
    first, second = held(s, brief_id)
    assert [r.built_as for r in second.revisions] == [bracket["variant_id"], changed["variant_id"]]
    assert second.latest.code == THICKER
    assert len(first.revisions) == 1
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    again = await s.call("build_variant", code=THICKER, brief_id=brief_id, slot=2)
    assert again["variant_id"] == changed["variant_id"]
    assert (again["variant_set"]["revision"], again["variant_set"]["already_member"]) == (2, True)
    assert len(held(s, brief_id)[1].revisions) == 2


async def test_a_full_set_takes_a_revision_in_a_slot_and_refuses_new_code_without_one(
    s: Session,
) -> None:
    brief_id = await s.confirmed_brief()
    key = store.confirmed_key(s.roots, brief_id)
    for number in range(MAX_MEMBERS):
        store.join(s.tmp / "projects", key, f"code {number}", VariantId("0" * 16))
    revised = await s.call("build_variant", code=PLATE, brief_id=brief_id, slot=3)
    assert (revised["variant_set"]["slot"], revised["variant_set"]["revision"]) == (3, 2)
    text = await s.refusal("build_variant", code=BRACKET, brief_id=brief_id)
    assert "SetFull" in text
    assert len(held(s, brief_id)) == MAX_MEMBERS


async def test_code_another_slot_already_shows_is_refused_before_any_container(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed_brief()
    await s.call("build_variant", code=PLATE, brief_id=brief_id)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id, slot=2)
    assert "SlotRefused: this code is already what slot 1 shows" in text
    assert len(held(s, brief_id)) == 1


async def test_a_slot_outside_the_set_is_refused_before_any_container(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed_brief()
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id, slot=6)
    assert "SlotRefused: slot 6 is not a slot" in text
    assert held(s, brief_id) == []


async def test_a_slot_without_a_brief_is_refused_before_any_container(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, slot=2)
    assert "SlotRefused" in text
    assert "brief_id" in text


async def test_a_revision_that_does_not_build_changes_nothing(s: Session) -> None:
    brief_id = await s.confirmed_brief()
    built = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    failed = await s.call("build_variant", code="x = 1\n", brief_id=brief_id, slot=1)
    assert failed["variant_set"]["kind"] == "not_joined"
    assert shows(s, brief_id) == [built["variant_id"]]


@pytest.mark.parametrize("slot", [True, "1", 1.0])
async def test_a_slot_that_is_not_a_whole_number_is_refused_before_any_container(
    s: Session, monkeypatch: pytest.MonkeyPatch, slot: object
) -> None:
    brief_id = await s.confirmed_brief()
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id, slot=slot)
    assert "slot" in text
    assert held(s, brief_id) == []
