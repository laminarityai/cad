from pathlib import Path

from binding import bind
from chain import Resolved
from provenance import Incomplete

from cad.checks.result import StepMissing
from cad.sandbox.outcome import Build, NoResult
from cad.variants import entry
from tests.support.cards import BREP_SHA, VARIANT_ID, genuine_card, result_of, trace


def test_a_card_with_no_results_is_incomplete_with_no_number(store: Path) -> None:
    traced = trace(genuine_card(results=()), store)
    assert Incomplete("the card has no results") in traced.failures
    assert Incomplete("the card holds no number") in traced.failures


def test_a_card_missing_a_registered_check_is_incomplete(store: Path) -> None:
    card = genuine_card()
    kept = tuple(result for result in card.results if result.check_id != "mass")
    traced = trace(card.model_copy(update={"results": kept}), store)
    assert Incomplete("no result for the registered check mass") in traced.failures
    assert all(isinstance(one.outcome, Resolved) for one in traced.numbers)


def test_a_card_with_a_check_twice_is_incomplete(store: Path) -> None:
    card = genuine_card()
    twice = (*card.results, result_of(card, "extents"))
    traced = trace(card.model_copy(update={"results": twice}), store)
    assert Incomplete("2 results for extents") in traced.failures


def test_a_card_whose_results_measure_nothing_is_incomplete(store: Path) -> None:
    card = genuine_card()
    emptied = tuple(result.model_copy(update={"measured": ()}) for result in card.results)
    traced = trace(card.model_copy(update={"results": emptied}), store)
    assert traced.failures == (Incomplete("the card holds no number"),)


def test_a_card_is_bound_to_the_shape_the_signed_build_stored(store: Path) -> None:
    assert bind(store, genuine_card()) is None
    unbound = bind(store, genuine_card(brep_sha256="f" * 64))
    assert unbound is not None and "the signed build stored" in unbound.reason


def test_a_card_with_no_build_record_is_unbound(tmp_path: Path) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    (tmp_path / "bare.key").write_bytes(b"k" * 32)
    (tmp_path / "bare.key").chmod(0o600)
    unbound = bind(root, genuine_card())
    assert unbound is not None and "no build record" in unbound.reason


def test_a_variant_directory_with_no_signed_record_is_unbound(tmp_path: Path) -> None:
    root = tmp_path / "unsigned"
    (root / VARIANT_ID).mkdir(parents=True)
    (tmp_path / "unsigned.key").write_bytes(b"k" * 32)
    (tmp_path / "unsigned.key").chmod(0o600)
    unbound = bind(root, genuine_card())
    assert unbound is not None and "did not sign" in unbound.reason


def test_a_store_without_a_key_is_unbound_and_no_key_is_made(tmp_path: Path) -> None:
    root = tmp_path / "keyless"
    root.mkdir()
    unbound = bind(root, genuine_card())
    assert unbound is not None and "no build record" in unbound.reason
    assert not (tmp_path / "keyless.key").exists()


def test_a_build_record_the_store_did_not_sign_is_unbound(store: Path) -> None:
    manifest = store / VARIANT_ID / entry.MANIFEST
    manifest.write_bytes(manifest.read_bytes().replace(BREP_SHA.encode(), b"f" * 64))
    unbound = bind(store, genuine_card(brep_sha256="f" * 64))
    assert unbound is not None and "did not sign" in unbound.reason


def test_a_build_without_a_shape_is_unbound(tmp_path: Path) -> None:
    root = tmp_path / "failed"
    root.mkdir()
    failed = Build(outcome=NoResult(reason="r"), output="")
    entry.save(root, entry.VariantId(VARIANT_ID), "x\n", failed, None)
    unbound = bind(root, genuine_card())
    assert unbound is not None and "without a shape" in unbound.reason


def test_a_stored_step_must_hash_to_the_one_on_the_card(store: Path) -> None:
    (store / VARIANT_ID / entry.STEP).write_bytes(b"another STEP")
    unbound = bind(store, genuine_card())
    assert unbound is not None and "names STEP" in unbound.reason


def test_a_stored_step_that_is_gone_is_unbound(store: Path) -> None:
    (store / VARIANT_ID / entry.STEP).unlink()
    unbound = bind(store, genuine_card())
    assert unbound is not None and "cannot be read" in unbound.reason


def test_a_card_with_no_step_needs_none_on_disk(store: Path) -> None:
    (store / VARIANT_ID / entry.STEP).unlink()
    assert bind(store, genuine_card(step=StepMissing(reason="none"))) is None
