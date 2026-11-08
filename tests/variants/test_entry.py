import hashlib
import json
import shutil
from pathlib import Path

import pytest

from cad.sandbox.outcome import Build, Built, NoResult, SandboxUnavailable
from cad.variants import entry, key
from cad.variants.entry import (
    NotBuilt,
    OutdatedVariant,
    StaleVariant,
    UnknownVariant,
    VariantId,
    open_entry,
    read_manifest,
    save,
    variant_id,
)

TAG = "cad-sandbox:test"
CODE = "result = Box(1, 1, 1)\n"
BREP = b"CASCADE Topology V3, (c) Open Cascade\n"
BUILT = Build(outcome=Built(), output="")


def stored(root: Path, code: str = CODE, brep: bytes = BREP) -> VariantId:
    vid = variant_id(code, TAG)
    save(root, vid, code, BUILT, brep)
    return vid


def test_a_stored_variant_opens_with_its_brep(tmp_path: Path) -> None:
    vid = stored(tmp_path)
    opened = open_entry(tmp_path, vid, TAG)
    assert (opened.id, opened.brep) == (vid, BREP)
    assert opened.brep_sha256 == hashlib.sha256(BREP).hexdigest()


def test_the_same_code_under_another_image_is_another_variant() -> None:
    assert variant_id(CODE, "cad-sandbox:a") != variant_id(CODE, "cad-sandbox:b")


@pytest.mark.parametrize(
    "raw",
    [
        "../outside",
        "..",
        "",
        "A" * 16,
        "a" * 15,
        "a" * 17,
        "a" * 15 + "\0",
        "/etc",
        "0123456789abcdeg",
    ],
)
def test_an_id_that_is_not_sixteen_lowercase_hex_is_refused_before_any_path_is_built(
    tmp_path: Path, raw: str
) -> None:
    root = tmp_path / "variants"
    outside = tmp_path / "outside"
    for directory in (root, outside):
        stored(directory)
    with pytest.raises(UnknownVariant):
        open_entry(root, raw, TAG)


def test_a_variant_that_was_never_stored_is_unknown(tmp_path: Path) -> None:
    with pytest.raises(UnknownVariant, match="0123456789abcdef"):
        open_entry(tmp_path, "0123456789abcdef", TAG)


def test_a_directory_named_by_the_old_key_is_stale_and_its_step_is_never_read(
    tmp_path: Path,
) -> None:
    old = tmp_path / "fe250eb62250be75"
    old.mkdir()
    (old / "code.py").write_text(CODE)
    (old / "build.json").write_text('{"outcome": {"kind": "built"}, "output": ""}')
    (old / "result.brep").write_bytes(BREP)
    (old / "result.step").write_bytes(b"FORGED-STEP")
    with pytest.raises(StaleVariant, match="variant fe250eb62250be75 was not stored by this"):
        open_entry(tmp_path, "fe250eb62250be75", TAG)


def test_an_entry_whose_code_was_edited_is_stale(tmp_path: Path) -> None:
    vid = stored(tmp_path)
    with (tmp_path / vid / "code.py").open("a") as code:
        code.write("# edited\n")
    with pytest.raises(StaleVariant, match=vid):
        open_entry(tmp_path, vid, TAG)


def test_an_entry_whose_code_is_not_utf8_is_stale(tmp_path: Path) -> None:
    vid = stored(tmp_path)
    (tmp_path / vid / "code.py").write_bytes(b"result = 1\xff\n")
    with pytest.raises(StaleVariant, match=vid):
        open_entry(tmp_path, vid, TAG)


def test_an_entry_whose_brep_was_swapped_is_stale(tmp_path: Path) -> None:
    vid = stored(tmp_path)
    (tmp_path / vid / "result.brep").write_bytes(BREP + b"x")
    with pytest.raises(StaleVariant, match=r"result\.brep"):
        open_entry(tmp_path, vid, TAG)


def test_an_entry_whose_brep_and_its_hash_were_both_rewritten_is_stale(tmp_path: Path) -> None:
    vid = stored(tmp_path)
    forged = BREP + b"another shape"
    (tmp_path / vid / "result.brep").write_bytes(forged)
    record = tmp_path / vid / "build.json"
    fields = json.loads(record.read_text())
    fields["brep_sha256"] = hashlib.sha256(forged).hexdigest()
    record.write_text(json.dumps(fields))
    with pytest.raises(StaleVariant, match=f"variant {vid} has a build record this store did not"):
        open_entry(tmp_path, vid, TAG)
    with pytest.raises(SandboxUnavailable, match=f"variant {vid} has a build record this store"):
        read_manifest(tmp_path, vid)


def test_a_build_record_copied_from_another_entry_is_stale(tmp_path: Path) -> None:
    vid = stored(tmp_path)
    other = stored(tmp_path, "result = Box(2, 2, 2)\n", BREP + b"another shape")
    for path in (tmp_path / other).iterdir():
        if path.name != "code.py":
            shutil.copyfile(path, tmp_path / vid / path.name)
    with pytest.raises(StaleVariant, match="did not sign"):
        open_entry(tmp_path, vid, TAG)


def test_an_entry_moved_into_another_store_is_stale(tmp_path: Path) -> None:
    vid = stored(tmp_path / "here")
    stored(tmp_path / "there", "result = Box(2, 2, 2)\n")
    shutil.copytree(tmp_path / "here" / vid, tmp_path / "there" / vid)
    with pytest.raises(StaleVariant, match="did not sign"):
        open_entry(tmp_path / "there", vid, TAG)


def test_an_entry_whose_brep_is_a_link_is_stale(tmp_path: Path) -> None:
    vid = stored(tmp_path)
    target = tmp_path / "elsewhere.brep"
    target.write_bytes(BREP)
    (tmp_path / vid / "result.brep").unlink()
    (tmp_path / vid / "result.brep").symlink_to(target)
    with pytest.raises(StaleVariant, match=r"result\.brep"):
        open_entry(tmp_path, vid, TAG)


def test_an_entry_with_an_unreadable_build_record_is_stale(tmp_path: Path) -> None:
    vid = stored(tmp_path)
    (tmp_path / vid / "build.json").write_text("{")
    with pytest.raises(StaleVariant, match="build record"):
        open_entry(tmp_path, vid, TAG)


def test_a_failed_build_has_no_shape_to_check(tmp_path: Path) -> None:
    vid = variant_id("x = 1\n", TAG)
    failure = Build(outcome=NoResult(reason="the code never assigned `result`"), output="")
    save(tmp_path, vid, "x = 1\n", failure, None)
    with pytest.raises(NotBuilt, match="ended as no_result"):
        open_entry(tmp_path, vid, TAG)


def test_a_step_attached_twice_leaves_one_file_and_the_last_bytes(tmp_path: Path) -> None:
    opened = open_entry(tmp_path, stored(tmp_path), TAG)
    assert opened.attach_step(b"STEP one") == hashlib.sha256(b"STEP one").hexdigest()
    assert opened.attach_step(b"STEP two") == hashlib.sha256(b"STEP two").hexdigest()
    assert (opened.directory / "result.step").read_bytes() == b"STEP two"
    assert sorted(path.name for path in opened.directory.iterdir()) == [
        "build.json",
        "build.mac",
        "code.py",
        "result.brep",
        "result.step",
    ]


def test_losing_a_save_race_returns_the_winners_manifest(tmp_path: Path) -> None:
    vid = stored(tmp_path)
    again = save(tmp_path, vid, CODE, Build(outcome=NoResult(reason="r"), output=""), None)
    assert again.outcome == Built()
    assert [path.name for path in tmp_path.iterdir()] == [vid]


def test_editing_any_trusted_file_re_keys_every_variant(tmp_path: Path) -> None:
    copies = tuple(tmp_path / directory.name for directory in entry.TRUSTED_DIRECTORIES)
    for source, copy in zip(entry.TRUSTED_DIRECTORIES, copies, strict=True):
        shutil.copytree(source, copy, ignore=shutil.ignore_patterns("__pycache__"))
    before = entry.trust_digest(copies)
    assert before == entry.TRUST_DIGEST
    (tmp_path / "sandbox" / "host.py").write_text("# a security fix\n")
    assert entry.trust_digest(copies) != before


def test_other_files_in_a_trusted_directory_do_not_re_key_variants(tmp_path: Path) -> None:
    (tmp_path / "trusted").mkdir()
    (tmp_path / "trusted" / "a.py").write_text("x = 1\n")
    before = entry.trust_digest((tmp_path / "trusted",))
    (tmp_path / "trusted" / "__pycache__").mkdir()
    (tmp_path / "trusted" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\0")
    (tmp_path / "trusted" / "notes.txt").write_text("x\n")
    assert entry.trust_digest((tmp_path / "trusted",)) == before


OLD_TAG = "cad-sandbox:before-a-deploy"


def stored_by_an_older_sandbox(root: Path) -> VariantId:
    vid = variant_id(CODE, OLD_TAG)
    save(root, vid, CODE, BUILT, BREP)
    return vid


def test_an_entry_stored_by_an_older_sandbox_hands_back_its_stored_code(tmp_path: Path) -> None:
    vid = stored_by_an_older_sandbox(tmp_path)
    with pytest.raises(OutdatedVariant) as raised:
        open_entry(tmp_path, vid, TAG)
    assert (raised.value.id, raised.value.code) == (vid, CODE)


def test_an_older_entry_whose_build_failed_hands_back_its_stored_code(tmp_path: Path) -> None:
    vid = variant_id(CODE, OLD_TAG)
    save(tmp_path, vid, CODE, Build(outcome=NoResult(reason="r"), output=""), None)
    with pytest.raises(OutdatedVariant) as raised:
        open_entry(tmp_path, vid, TAG)
    assert raised.value.code == CODE


def test_an_older_entry_with_a_record_copied_from_another_entry_is_refused(
    tmp_path: Path,
) -> None:
    vid = stored_by_an_older_sandbox(tmp_path)
    other = variant_id("result = Box(2, 2, 2)\n", OLD_TAG)
    save(tmp_path, other, "result = Box(2, 2, 2)\n", BUILT, BREP)
    for name in ("code.py", "build.json", "build.mac"):
        shutil.copyfile(tmp_path / other / name, tmp_path / vid / name)
    with pytest.raises(StaleVariant, match=f"variant {vid} was not stored by this") as raised:
        open_entry(tmp_path, vid, TAG)
    assert not isinstance(raised.value, OutdatedVariant)


@pytest.mark.parametrize("name", ["code.py", "build.json", "build.mac"])
def test_an_older_entry_with_a_linked_file_is_refused(tmp_path: Path, name: str) -> None:
    vid = stored_by_an_older_sandbox(tmp_path)
    target = tmp_path / f"elsewhere-{name}"
    (tmp_path / vid / name).rename(target)
    (tmp_path / vid / name).symlink_to(target)
    with pytest.raises(StaleVariant, match=vid) as raised:
        open_entry(tmp_path, vid, TAG)
    assert not isinstance(raised.value, OutdatedVariant)


def test_an_older_entry_with_no_build_mac_is_refused(tmp_path: Path) -> None:
    vid = stored_by_an_older_sandbox(tmp_path)
    (tmp_path / vid / "build.mac").unlink()
    with pytest.raises(StaleVariant, match=f"variant {vid} was not stored by this") as raised:
        open_entry(tmp_path, vid, TAG)
    assert not isinstance(raised.value, OutdatedVariant)


def test_an_older_entry_whose_code_was_edited_is_refused_and_not_rebuilt(tmp_path: Path) -> None:
    vid = stored_by_an_older_sandbox(tmp_path)
    (tmp_path / vid / "code.py").write_text("result = Box(9, 9, 9)\n")
    with pytest.raises(
        StaleVariant, match=f"variant {vid} has a code.py that was altered"
    ) as raised:
        open_entry(tmp_path, vid, TAG)
    assert not isinstance(raised.value, OutdatedVariant)


def test_an_older_entry_stored_before_rebuilds_is_refused_and_not_rebuilt(tmp_path: Path) -> None:
    vid = stored_by_an_older_sandbox(tmp_path)
    record = json.dumps({"outcome": {"kind": "built"}, "output": "", "brep_sha256": "0" * 64})
    (tmp_path / vid / "build.json").write_text(record)
    (tmp_path / vid / "build.mac").write_bytes(key.sign(tmp_path, vid, record.encode()))
    with pytest.raises(StaleVariant, match=f"variant {vid} was stored before") as raised:
        open_entry(tmp_path, vid, TAG)
    assert not isinstance(raised.value, OutdatedVariant)
