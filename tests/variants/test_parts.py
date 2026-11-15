"""The parts a build reads are part of what its id and signed record name (ADR-0012)."""

import hashlib
import json
from pathlib import Path

import pytest

from cad.sandbox.outcome import Build, Built, PartPlacement, PartUse
from cad.variants import entry
from cad.variants.entry import (
    OutdatedVariant,
    build_sha256,
    built_from,
    open_entry,
    read_manifest,
    save,
    variant_id,
)

TAG = "cad-sandbox:test"
OLD_TAG = "cad-sandbox:before-an-update"
CODE = "result = Box(1, 1, 1)\n"
BREP = b"CASCADE Topology V3, (c) Open Cascade\n"
BUILT = Build(outcome=Built(), output="")
WHEEL = PartUse(
    part_id="part-0123456789abcdef",
    project="p-0123456789abcdef",
    brep_sha256="a" * 64,
    placements=(PartPlacement(at=(10, 0, 0)), PartPlacement(at=(-10, 0, 0), rotate=(0, 0, 90))),
)


def stored(root: Path, parts: tuple[PartUse, ...], tag: str = TAG) -> entry.VariantId:
    vid = variant_id(CODE, tag, parts)
    save(root, vid, CODE, BUILT, BREP, parts)
    return vid


def test_code_that_reads_no_part_keeps_the_id_it_had_before_parts() -> None:
    before = json.dumps([TAG, entry.TRUST_DIGEST, CODE])
    assert variant_id(CODE, TAG) == hashlib.sha256(before.encode()).hexdigest()[:16]
    assert build_sha256(CODE) == hashlib.sha256(CODE.encode()).hexdigest()


@pytest.mark.parametrize(
    "changed",
    [
        WHEEL.model_copy(update={"brep_sha256": "b" * 64}),
        WHEEL.model_copy(update={"part_id": "part-fedcba9876543210"}),
        WHEEL.model_copy(update={"placements": WHEEL.placements[:1]}),
        WHEEL.model_copy(update={"placements": (PartPlacement(at=(10, 0, 0.5)),)}),
        WHEEL.model_copy(update={"placements": ()}),
    ],
)
def test_each_part_hash_and_placement_is_in_the_id(changed: PartUse) -> None:
    ids = {
        variant_id(CODE, TAG),
        variant_id(CODE, TAG, (WHEEL,)),
        variant_id(CODE, TAG, (changed,)),
    }
    assert len(ids) == 3
    builds = {build_sha256(CODE), build_sha256(CODE, (WHEEL,)), build_sha256(CODE, (changed,))}
    assert len(builds) == 3


def test_the_project_a_part_is_fetched_from_is_not_in_the_id() -> None:
    moved = WHEEL.model_copy(update={"project": "p-ffffffffffffffff"})
    assert variant_id(CODE, TAG, (moved,)) == variant_id(CODE, TAG, (WHEEL,))
    assert build_sha256(CODE, (moved,)) == build_sha256(CODE, (WHEEL,))


def test_a_stored_variant_signs_and_opens_with_the_parts_it_read(tmp_path: Path) -> None:
    vid = stored(tmp_path, (WHEEL,))
    assert open_entry(tmp_path, vid, TAG).parts == (WHEEL,)
    manifest = read_manifest(tmp_path, vid)
    assert manifest is not None
    assert manifest.parts == (WHEEL,)


def test_a_record_of_a_build_that_read_no_part_has_no_parts_field(tmp_path: Path) -> None:
    vid = stored(tmp_path, ())
    assert b"parts" not in (tmp_path / vid / entry.MANIFEST).read_bytes()
    assert open_entry(tmp_path, vid, TAG).parts == ()


def test_the_index_keeps_code_with_parts_apart_from_the_same_code_without(
    tmp_path: Path,
) -> None:
    plain = stored(tmp_path, ())
    placed = stored(tmp_path, (WHEEL,))
    assert built_from(tmp_path, CODE) == (plain,)
    assert built_from(tmp_path, CODE, (WHEEL,)) == (placed,)


def test_an_outdated_entry_hands_back_the_parts_it_read(tmp_path: Path) -> None:
    vid = stored(tmp_path, (WHEEL,), tag=OLD_TAG)
    with pytest.raises(OutdatedVariant) as raised:
        open_entry(tmp_path, vid, TAG)
    assert (raised.value.code, raised.value.parts) == (CODE, (WHEEL,))
