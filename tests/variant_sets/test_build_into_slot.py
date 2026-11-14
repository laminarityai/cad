from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cad.checks.lanes import LANES
from cad.variant_sets import store
from cad.variant_sets.model import MAX_MEMBERS
from cad.variants.entry import VariantId
from tests.support.set_parts import BRACKET, NO_DOCKER, PLATE, THICKER, held, shows

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

    from tests.support.variant_set_session import Session

pytestmark = [pytest.mark.anyio, pytest.mark.docker]


async def test_a_change_to_slot_2_becomes_its_next_revision_and_the_old_one_stays_in_history(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief_id = await s.confirmed_brief()
    await s.call("build_variant", code=PLATE, brief_id=brief_id)
    bracket = await s.call("build_variant", code=BRACKET, brief_id=brief_id)
    assert bracket["variant_set"]["slot"] == 2
    changed = await s.call("build_variant", code=THICKER, brief_id=brief_id, slot=2)
    assert changed["outcome"] == {"kind": "built", "areas": [], "areas_dropped": None}
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


async def test_a_coloured_revision_joins_its_slot(s: Session) -> None:
    brief_id = await s.confirmed_brief()
    await s.call("build_variant", code=PLATE, brief_id=brief_id)
    painted = THICKER + (
        'from build123d import Color\nresult.color = Color("gray")\nresult.label = "steel plate"\n'
    )
    changed = await s.call("build_variant", code=painted, brief_id=brief_id, slot=1)
    assert changed["outcome"]["areas"][0]["name"] == "steel plate"
    assert changed["variant_set"]["kind"] == "joined"
    assert held(s, brief_id)[0].latest.code == painted


async def test_a_revision_drops_the_unstarted_checks_of_the_one_it_replaced_and_nothing_else(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    dropped: list[tuple[Path, str]] = []

    def record(root: Path, replaced: Callable[[], Collection[str]]) -> int:
        dropped.extend((root, one) for one in replaced())
        return 0

    monkeypatch.setattr(LANES, "drop_unstarted", record)
    brief_id = await s.confirmed_brief()
    first = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    assert dropped == []
    await s.call("build_variant", code=PLATE, brief_id=brief_id)
    await s.call("build_variant", code=BRACKET, brief_id=brief_id)
    assert dropped == []
    second = await s.call("build_variant", code=THICKER, brief_id=brief_id, slot=1)
    assert dropped == [(s.tmp / "variants", first["variant_id"])]
    await s.call("build_variant", code="x = 1\n", brief_id=brief_id, slot=1)
    assert len(dropped) == 1
    assert second["variant_id"] not in {variant for _, variant in dropped}


async def test_a_slot_replaced_twice_drops_every_earlier_revision_it_still_has_queued(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    dropped: set[str] = set()

    def record(root: Path, replaced: Callable[[], Collection[str]]) -> int:
        dropped.update(replaced())
        return 0

    monkeypatch.setattr(LANES, "drop_unstarted", record)
    brief_id = await s.confirmed_brief()
    first = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    second = await s.call("build_variant", code=THICKER, brief_id=brief_id, slot=1)
    third = await s.call(
        "build_variant", code=PLATE + "\n# thicker still\n", brief_id=brief_id, slot=1
    )
    assert dropped == {first["variant_id"], second["variant_id"]}
    assert third["variant_id"] not in dropped


async def test_an_old_revision_that_another_slot_now_shows_keeps_its_queued_checks(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    dropped: set[str] = set()

    def record(root: Path, replaced: Callable[[], Collection[str]]) -> int:
        dropped.update(replaced())
        return 0

    monkeypatch.setattr(LANES, "drop_unstarted", record)
    brief_id = await s.confirmed_brief()
    plate = await s.call("build_variant", code=PLATE, brief_id=brief_id, slot=1)
    thicker = await s.call("build_variant", code=THICKER, brief_id=brief_id, slot=1)
    again = await s.call("build_variant", code=PLATE, brief_id=brief_id, slot=2)
    assert again["variant_id"] == plate["variant_id"]
    dropped.clear()
    await s.call("build_variant", code=BRACKET, brief_id=brief_id, slot=1)
    assert plate["variant_id"] in shows(s, brief_id)
    assert dropped == {thicker["variant_id"]}


async def test_a_revision_keeps_the_queued_checks_of_a_variant_another_brief_still_shows(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    dropped: set[str] = set()

    def record(root: Path, replaced: Callable[[], Collection[str]]) -> int:
        dropped.update(replaced())
        return 0

    monkeypatch.setattr(LANES, "drop_unstarted", record)
    mine, theirs = await s.confirmed_brief(), await s.confirmed_brief()
    plate = await s.call("build_variant", code=PLATE, brief_id=mine)
    shared = await s.call("build_variant", code=PLATE, brief_id=theirs)
    assert shared["variant_id"] == plate["variant_id"]
    thicker = await s.call("build_variant", code=THICKER, brief_id=mine, slot=1)
    assert plate["variant_id"] in shows(s, theirs)
    assert dropped == set()
    await s.call("build_variant", code=BRACKET, brief_id=theirs, slot=1)
    assert dropped == {plate["variant_id"]}
    assert thicker["variant_id"] in shows(s, mine)


async def test_a_full_set_takes_a_revision_in_a_slot_and_refuses_new_code_without_one(
    s: Session,
) -> None:
    brief_id = await s.confirmed_brief()
    key = store.set_key(s.roots, brief_id)
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
