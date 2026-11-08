import json
from pathlib import Path

from binding import Unlinked, link
from cards import VARIANT_ID, genuine_card, trace

from cad.sandbox.outcome import Build, Built
from cad.variants import entry, key

OLD_ID = "fedcba9876543210"


def stored_old(root: Path, code: str) -> None:
    entry.save(root, entry.VariantId(OLD_ID), code, Build(outcome=Built(), output=""), b"old")


def test_a_card_rebuilt_from_an_entry_that_stored_the_same_code_is_linked(store: Path) -> None:
    stored_old(store, "x = 1\n")
    card = genuine_card(rebuilt_from=OLD_ID)
    assert link(store, card) is None
    assert not any(isinstance(one, Unlinked) for one in trace(card, store).failures)


def test_a_card_that_was_not_rebuilt_needs_no_link(tmp_path: Path) -> None:
    assert link(tmp_path, genuine_card()) is None
    assert not (tmp_path.parent / f"{tmp_path.name}.key").exists()


def test_a_card_rebuilt_from_an_entry_with_other_code_is_unlinked(store: Path) -> None:
    stored_old(store, "x = 2\n")
    traced = trace(genuine_card(rebuilt_from=OLD_ID), store)
    reason = f"variant {VARIANT_ID} was not built from the code that {OLD_ID} stored"
    assert Unlinked(reason) in traced.failures


def test_a_card_rebuilt_from_an_entry_that_is_gone_is_unlinked(store: Path) -> None:
    unlinked = link(store, genuine_card(rebuilt_from=OLD_ID))
    assert unlinked == Unlinked(f"the card says it was rebuilt from {OLD_ID}, which pins no code")


def test_a_card_rebuilt_from_an_entry_stored_before_code_hashes_is_unlinked(store: Path) -> None:
    stored_old(store, "x = 1\n")
    record = json.dumps({"outcome": {"kind": "built"}, "output": "", "brep_sha256": "0" * 64})
    (store / OLD_ID / entry.MANIFEST).write_text(record)
    (store / OLD_ID / entry.MAC).write_bytes(key.sign(store, OLD_ID, record.encode()))
    unlinked = link(store, genuine_card(rebuilt_from=OLD_ID))
    assert unlinked is not None and "pins no code" in unlinked.reason


def test_a_card_rebuilt_from_an_entry_with_an_unsigned_record_is_unlinked(store: Path) -> None:
    stored_old(store, "x = 1\n")
    (store / OLD_ID / entry.MAC).unlink()
    unlinked = link(store, genuine_card(rebuilt_from=OLD_ID))
    assert unlinked is not None and "did not sign" in unlinked.reason


def test_a_store_without_a_key_is_unlinked_and_no_key_is_made(tmp_path: Path) -> None:
    root = tmp_path / "keyless"
    root.mkdir()
    unlinked = link(root, genuine_card(rebuilt_from=OLD_ID))
    assert unlinked is not None and "no key" in unlinked.reason
    assert not (tmp_path / "keyless.key").exists()


def test_a_malformed_rebuilt_from_is_unlinked(store: Path) -> None:
    unlinked = link(store, genuine_card(rebuilt_from="../elsewhere"))
    assert unlinked is not None and "../elsewhere" in unlinked.reason
