import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cad.briefs.model import BriefId
from cad.checks import report
from cad.projects.model import ProjectId
from cad.variant_sets import store
from cad.variant_sets.model import MAX_MEMBERS, Joined, SetFull, SetKey, TamperedSet
from cad.variants import entry
from cad.variants.entry import VariantId

KEY = SetKey(ProjectId("p-" + "1" * 16), BriefId("2" * 16), "3" * 64)


def join(root: Path, code: str, key: SetKey = KEY) -> Joined:
    return store.join(root, key, code, VariantId("4" * 16))


def test_the_same_code_keeps_its_slot(tmp_path: Path) -> None:
    assert join(tmp_path, "a").slot == 1
    assert join(tmp_path, "b").slot == 2
    again = join(tmp_path, "a")
    assert (again.slot, again.already_member) == (1, True)
    assert [m.code for m in store.members(tmp_path, KEY)] == ["a", "b"]


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
    held = [m.code for m in store.members(tmp_path, KEY)]
    assert sorted(held) == ["code 0", "code 1", "code 2"]
    assert all(held[slot - 1] == code for code, slot in zip(codes, slots, strict=True))


def test_a_set_has_no_members_until_one_joins(tmp_path: Path) -> None:
    assert store.members(tmp_path, KEY) == ()


def test_a_tampered_member_names_the_brief_and_no_host_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    join(tmp_path, "a")
    [member] = (tmp_path / KEY.project / KEY.brief_id / KEY.decision_sha256).iterdir()
    member.write_bytes(member.read_bytes().replace(b'"a"', b'"b"'))
    for attempt in (lambda: store.members(tmp_path, KEY), lambda: join(tmp_path, "c")):
        with pytest.raises(TamperedSet) as refused:
            attempt()
        assert KEY.brief_id in str(refused.value)
        assert str(tmp_path) not in str(refused.value)
    assert str(tmp_path) in caplog.text


def test_a_member_copied_into_another_set_is_tampering(tmp_path: Path) -> None:
    other = SetKey(KEY.project, KEY.brief_id, "5" * 64)
    join(tmp_path, "a")
    join(tmp_path, "b", other)
    source = tmp_path / KEY.project / KEY.brief_id
    shutil.copy(source / KEY.decision_sha256 / "0001.signed", source / other.decision_sha256)
    with pytest.raises(TamperedSet):
        store.members(tmp_path, other)


def test_no_variant_set_code_feeds_a_variant_id_or_a_check_version() -> None:
    directory = Path(store.__file__).parent
    assert directory not in entry.TRUSTED_DIRECTORIES
    assert [f for f in report.DEPENDENCIES.files if f.startswith("cad/variant_sets/")] == []
