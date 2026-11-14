import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cad.briefs.model import BriefId
from cad.checks import report
from cad.projects.model import ProjectId
from cad.variant_sets import store
from cad.variant_sets.model import (
    MAX_MEMBERS,
    Joined,
    SetFull,
    SetKey,
    SlotRefused,
    TamperedSet,
)
from cad.variants import entry
from cad.variants.entry import VariantId

KEY = SetKey(ProjectId("p-" + "1" * 16), BriefId("2" * 16))


def join(root: Path, code: str, key: SetKey = KEY, slot: int | None = None) -> Joined:
    return store.join(root, key, code, VariantId("4" * 16), slot)


def shown(root: Path, key: SetKey = KEY) -> list[str]:
    return [m.latest.code for m in store.members(root, key)]


def members_directory(root: Path, key: SetKey) -> Path:
    return root / key.project / "sets" / key.brief_id / "revisions"


def test_a_set_lives_in_the_project_store_and_signs_with_the_projects_key(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    join(root, "a")
    assert (members_directory(root, KEY) / "0001.signed").is_file()
    assert (tmp_path / "projects.key").is_file()
    assert not (tmp_path / "variant_sets.key").exists()


def test_the_same_code_keeps_its_slot(tmp_path: Path) -> None:
    assert join(tmp_path, "a").slot == 1
    assert join(tmp_path, "b").slot == 2
    again = join(tmp_path, "a")
    assert (again.slot, again.already_member) == (1, True)
    assert shown(tmp_path) == ["a", "b"]


def test_a_sixth_distinct_member_is_refused(tmp_path: Path) -> None:
    for number in range(MAX_MEMBERS):
        join(tmp_path, f"code {number}")
    with pytest.raises(SetFull, match=f"brief {KEY.brief_id} holds 5 variants, its limit"):
        join(tmp_path, "one too many")
    assert join(tmp_path, "code 4").slot == MAX_MEMBERS
    assert len(store.members(tmp_path, KEY)) == MAX_MEMBERS


def test_concurrent_builds_take_one_slot_each(tmp_path: Path) -> None:
    codes = [f"code {n % 3}" for n in range(12)]

    def slot(code: str) -> int:
        return join(tmp_path, code).slot

    with ThreadPoolExecutor(max_workers=len(codes)) as pool:
        slots = list(pool.map(slot, codes))
    held = shown(tmp_path)
    assert sorted(held) == ["code 0", "code 1", "code 2"]
    assert all(held[slot - 1] == code for code, slot in zip(codes, slots, strict=True))


def test_a_set_that_filled_while_building_names_the_built_variant(tmp_path: Path) -> None:
    for number in range(MAX_MEMBERS):
        join(tmp_path, f"code {number}")
    with pytest.raises(SetFull) as refused:
        store.join(tmp_path, KEY, "late", VariantId("a" * 16))
    assert "a" * 16 in str(refused.value)
    assert "not built" not in str(refused.value)
    assert "filled while" in str(refused.value)


def test_a_set_has_no_members_until_one_joins(tmp_path: Path) -> None:
    assert store.members(tmp_path, KEY) == ()


@pytest.mark.parametrize(
    "old_path",
    [
        ("7" * 64, "members"),
        ("2" * 16, "7" * 64, "members"),
        ("2" * 16, "7" * 64, "revisions"),
    ],
    ids=["by decision", "by brief and decision", "by brief, decision and revisions"],
)
def test_a_set_saved_under_an_old_layout_is_not_read_and_reads_as_empty(
    tmp_path: Path, old_path: tuple[str, ...]
) -> None:
    old = tmp_path / KEY.project / "sets" / Path(*old_path)
    old.mkdir(parents=True)
    (old / "0001.signed").write_bytes(b"x")
    assert store.members(tmp_path, KEY) == ()
    assert store.project_slots(tmp_path, KEY.project) == ()
    assert join(tmp_path, "a").slot == 1
    assert shown(tmp_path) == ["a"]


def test_a_tampered_member_names_the_brief_and_no_host_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    join(tmp_path, "a")
    [record] = members_directory(tmp_path, KEY).iterdir()
    record.write_bytes(record.read_bytes().replace(b'"a"', b'"b"'))
    for attempt in (lambda: store.members(tmp_path, KEY), lambda: join(tmp_path, "c")):
        with pytest.raises(TamperedSet) as refused:
            attempt()
        assert KEY.brief_id in str(refused.value)
        assert str(tmp_path) not in str(refused.value)
    assert str(tmp_path) in caplog.text


def test_a_member_copied_into_another_brief_is_tampering(tmp_path: Path) -> None:
    other = SetKey(KEY.project, BriefId("6" * 16))
    join(tmp_path, "a")
    join(tmp_path, "b", other)
    shutil.copy(
        members_directory(tmp_path, KEY) / "0001.signed", members_directory(tmp_path, other)
    )
    with pytest.raises(TamperedSet):
        store.members(tmp_path, other)


def test_a_revision_replaces_what_its_slot_shows_and_keeps_the_old_one_in_its_history(
    tmp_path: Path,
) -> None:
    join(tmp_path, "wall 3 mm")
    store.join(tmp_path, KEY, "wall 4 mm", VariantId("5" * 16), 1)
    revised = store.join(tmp_path, KEY, "wall 5 mm", VariantId("6" * 16), 1)
    assert (revised.slot, revised.revision, revised.already_member) == (1, 3, False)
    [member] = store.members(tmp_path, KEY)
    assert member.slot == 1
    assert [r.code for r in member.revisions] == ["wall 3 mm", "wall 4 mm", "wall 5 mm"]
    assert [r.built_as for r in member.revisions] == ["4" * 16, "5" * 16, "6" * 16]
    assert member.latest.code == "wall 5 mm"


def test_revising_one_slot_leaves_the_others_alone(tmp_path: Path) -> None:
    for code in ("a", "b", "c"):
        join(tmp_path, code)
    join(tmp_path, "b2", slot=2)
    assert shown(tmp_path) == ["a", "b2", "c"]
    assert [len(m.revisions) for m in store.members(tmp_path, KEY)] == [1, 2, 1]


def test_a_full_set_still_takes_a_revision_but_not_new_code(tmp_path: Path) -> None:
    for number in range(MAX_MEMBERS):
        join(tmp_path, f"code {number}")
    revised = join(tmp_path, "code 2, thicker", slot=3)
    assert (revised.slot, revised.revision) == (3, 2)
    with pytest.raises(SetFull):
        join(tmp_path, "one too many")
    with pytest.raises(SetFull):
        join(tmp_path, "one too many", slot=None)
    assert len(store.members(tmp_path, KEY)) == MAX_MEMBERS


def test_building_the_slots_current_code_again_adds_no_revision(tmp_path: Path) -> None:
    join(tmp_path, "a")
    join(tmp_path, "a2", slot=1)
    again = join(tmp_path, "a2", slot=1)
    assert (again.slot, again.revision, again.already_member) == (1, 2, True)
    assert len(list(members_directory(tmp_path, KEY).iterdir())) == 2


def test_going_back_to_an_earlier_revision_adds_one_that_shows_it(tmp_path: Path) -> None:
    join(tmp_path, "a")
    join(tmp_path, "a2", slot=1)
    back = join(tmp_path, "a", slot=1)
    assert (back.revision, back.already_member) == (3, False)
    assert shown(tmp_path) == ["a"]


def test_old_code_with_no_slot_is_new_code_once_a_revision_replaced_it(tmp_path: Path) -> None:
    join(tmp_path, "a")
    join(tmp_path, "a2", slot=1)
    joined = join(tmp_path, "a")
    assert (joined.slot, joined.revision) == (2, 1)


def test_a_free_slot_can_be_named_and_unslotted_code_takes_the_lowest_free_one(
    tmp_path: Path,
) -> None:
    named = join(tmp_path, "b", slot=2)
    assert (named.slot, named.revision, named.already_member) == (2, 1, False)
    assert join(tmp_path, "a").slot == 1
    assert join(tmp_path, "c").slot == 3
    assert [m.slot for m in store.members(tmp_path, KEY)] == [1, 2, 3]


@pytest.mark.parametrize("slot", [0, 6])
def test_a_slot_outside_one_to_five_is_refused_and_writes_nothing(
    tmp_path: Path, slot: int
) -> None:
    join(tmp_path, "a")
    with pytest.raises(SlotRefused, match="a set has slots 1 to 5"):
        join(tmp_path, "b", slot=slot)
    assert shown(tmp_path) == ["a"]


def test_code_shown_in_another_slot_is_refused_for_this_one(tmp_path: Path) -> None:
    join(tmp_path, "a")
    join(tmp_path, "b")
    with pytest.raises(SlotRefused, match="already what slot 1 shows"):
        join(tmp_path, "a", slot=2)
    assert shown(tmp_path) == ["a", "b"]


def test_concurrent_revisions_of_one_slot_all_land_in_its_history(tmp_path: Path) -> None:
    join(tmp_path, "start")
    codes = [f"revision {n}" for n in range(6)]

    def revise(code: str) -> int:
        return join(tmp_path, code, slot=1).revision

    with ThreadPoolExecutor(max_workers=len(codes)) as pool:
        revisions = sorted(pool.map(revise, codes))
    [member] = store.members(tmp_path, KEY)
    assert revisions == list(range(2, 8))
    assert sorted(r.code for r in member.revisions[1:]) == sorted(codes)
    assert member.latest.code == member.revisions[-1].code


def test_a_revision_cannot_be_moved_to_another_slot_by_editing_its_record(
    tmp_path: Path,
) -> None:
    join(tmp_path, "a")
    join(tmp_path, "b")
    [record] = [p for p in members_directory(tmp_path, KEY).iterdir() if p.name == "0002.signed"]
    record.write_bytes(record.read_bytes().replace(b'"slot":2', b'"slot":1'))
    with pytest.raises(TamperedSet):
        store.members(tmp_path, KEY)


def test_no_variant_set_code_feeds_a_variant_id_or_a_check_version() -> None:
    directory = Path(store.__file__).parent
    assert directory.name not in {name.split("/")[0] for name in entry.TRUSTED_FILES}
    assert [f for f in report.DEPENDENCIES.files if f.startswith("cad/variant_sets/")] == []
