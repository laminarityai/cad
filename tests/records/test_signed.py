import hashlib
import hmac
import shutil
from pathlib import Path

import pytest

from cad.briefs import store
from cad.checks import report
from cad.records import signed
from cad.records.roots import Roots
from cad.records.signed import Appended, Full, Store
from cad.variants import entry

LEGACY = Path(__file__).parent / "legacy"
LEGACY_KEY = bytes(range(32))


def slot_of(number: int) -> str:
    return f"thing/{number}"


def legacy_copy(tmp_path: Path) -> Path:
    shutil.copytree(LEGACY, tmp_path / "legacy")
    copied = tmp_path / "legacy"
    (copied / "briefs.key").chmod(0o600)
    return copied / "briefs"


def append_text(things: Store, directory: Path, text: str, cap: int | None = None):
    return signed.append(things, directory, slot_of, lambda _existing: text.encode(), cap)


@pytest.fixture
def things(tmp_path: Path) -> Store:
    (tmp_path / "things" / "a").mkdir(parents=True)
    return Store(tmp_path / "things", "thing")


def test_a_brief_signed_by_the_old_code_still_verifies(tmp_path: Path) -> None:
    root = legacy_copy(tmp_path)
    [brief_id] = [path.name for path in root.iterdir()]
    roots = Roots(root, tmp_path / "projects")
    state = store.read_state(roots, brief_id)
    assert [p.status for p in state.proposals] == [store.Status.CONFIRMED]
    confirmed = store.confirmed_requirements(roots, brief_id)
    decision = (root / brief_id / store.DECISIONS / "0001.signed").read_bytes()
    assert confirmed is not None
    assert confirmed.decision_sha256 == hashlib.sha256(decision.partition(b"\n")[2]).hexdigest()
    assert [r.origin.end - r.origin.start for r in confirmed.requirements] == [len("under 150 g")]


def test_a_signature_is_the_hmac_of_the_slot_a_null_byte_and_the_record(tmp_path: Path) -> None:
    root = legacy_copy(tmp_path)
    [brief_id] = [path.name for path in root.iterdir()]
    on_disk = (root / brief_id / store.BRIEF).read_bytes()
    mac, _, record = on_disk.partition(b"\n")
    expected = hmac.new(LEGACY_KEY, f"{brief_id}/brief".encode() + b"\0" + record, hashlib.sha256)
    assert mac == expected.hexdigest().encode()
    assert signed.signed(Store(root, "brief"), f"{brief_id}/brief", record) == on_disk


def test_a_record_moved_to_another_slot_fails(things: Store) -> None:
    path = things.root / "a" / "0001.signed"
    assert signed.publish(things, "thing/1", path, b"record")
    assert signed.read(things, "thing/1", path) == b"record"
    assert signed.read(things, "thing/2", path) is None


def test_the_first_writer_of_a_slot_wins(things: Store) -> None:
    path = things.root / "a" / "0001.signed"
    assert signed.publish(things, "thing/1", path, b"first")
    assert not signed.publish(things, "thing/1", path, b"second")
    assert signed.read(things, "thing/1", path) == b"first"
    assert [p.name for p in path.parent.iterdir()] == ["0001.signed"]


def test_an_unusable_key_names_the_store(tmp_path: Path, things: Store) -> None:
    signed.publish(things, "thing/1", things.root / "a" / "0001.signed", b"record")
    (tmp_path / "things.key").chmod(0o644)
    with pytest.raises(signed.StoreUnusable, match="the thing store's key is unusable"):
        signed.read(things, "thing/1", things.root / "a" / "0001.signed")


def test_key_exists_does_not_create_the_key(tmp_path: Path) -> None:
    things = Store(tmp_path / "things", "thing")
    assert not things.key_exists()
    assert not (tmp_path / "things.key").exists()
    signed.signed(things, "thing/1", b"record")
    assert things.key_exists()


def test_an_entry_appears_whole_and_only_once(tmp_path: Path) -> None:
    things = Store(tmp_path / "things", "thing")
    first = ("x/top", "top.signed", b"top")
    assert signed.create_entry(things, "x", first, ("one", "two"))
    assert sorted(p.name for p in (things.root / "x").iterdir()) == ["one", "top.signed", "two"]
    assert signed.read(things, "x/top", things.root / "x" / "top.signed") == b"top"
    assert not signed.create_entry(things, "x", ("x/top", "top.signed", b"again"), ("one",))
    assert [p.name for p in things.root.iterdir()] == ["x"]
    assert signed.read(things, "x/top", things.root / "x" / "top.signed") == b"top"


def test_append_takes_numbered_slots_in_order(things: Store) -> None:
    directory = things.root / "a"
    assert append_text(things, directory, "one") == Appended(1)
    assert append_text(things, directory, "two") == Appended(2)
    assert signed.read_numbered(things, directory, slot_of) == (b"one", b"two")


def test_append_stops_at_the_cap(things: Store) -> None:
    directory = things.root / "a"
    append_text(things, directory, "one", cap=1)
    assert append_text(things, directory, "two", cap=1) == Full(1)
    assert signed.read_numbered(things, directory, slot_of) == (b"one",)


def test_append_writes_nothing_when_the_hook_declines(things: Store) -> None:
    directory = things.root / "a"
    append_text(things, directory, "one")
    seen: list[tuple[bytes, ...]] = []

    def decline(existing: tuple[bytes, ...]) -> None:
        seen.append(existing)

    assert signed.append(things, directory, slot_of, decline) is None
    assert seen == [(b"one",)]
    assert signed.read_numbered(things, directory, slot_of) == (b"one",)


def test_append_retries_after_losing_a_race(things: Store) -> None:
    directory = things.root / "a"
    calls = 0

    def rival_then_mine(existing: tuple[bytes, ...]) -> bytes:
        nonlocal calls
        calls += 1
        if calls == 1:
            signed.publish(things, slot_of(1), directory / "0001.signed", b"rival")
        return b"mine"

    assert signed.append(things, directory, slot_of, rival_then_mine) == Appended(2)
    assert signed.read_numbered(things, directory, slot_of) == (b"rival", b"mine")


def test_append_gives_up_when_every_attempt_loses(things: Store) -> None:
    directory = things.root / "a"

    def always_beaten(existing: tuple[bytes, ...]) -> bytes:
        number = len(existing) + 1
        signed.publish(things, slot_of(number), directory / f"{number:04d}.signed", b"rival")
        return b"mine"

    with pytest.raises(signed.Contended):
        signed.append(things, directory, slot_of, always_beaten)


def test_a_slot_with_a_hole_is_tampering(things: Store) -> None:
    directory = things.root / "a"
    append_text(things, directory, "one")
    append_text(things, directory, "two")
    (directory / "0001.signed").unlink()
    assert signed.read_numbered(things, directory, slot_of) is None
    with pytest.raises(signed.Tampered):
        append_text(things, directory, "three")


def test_a_swapped_slot_is_tampering(things: Store) -> None:
    directory = things.root / "a"
    append_text(things, directory, "one")
    append_text(things, directory, "two")
    one, two = directory / "0001.signed", directory / "0002.signed"
    swap = directory / "swap"
    one.rename(swap)
    two.rename(one)
    swap.rename(two)
    assert signed.read_numbered(things, directory, slot_of) is None


def test_no_signed_record_code_feeds_a_variant_id_or_a_check_version() -> None:
    records_directory = Path(signed.__file__).parent
    assert records_directory not in entry.TRUSTED_DIRECTORIES
    feeding = [f for f in report.DEPENDENCIES.files if f.startswith("cad/records/")]
    assert feeding == ["cad/records/__init__.py", "cad/records/files.py", "cad/records/key.py"]
