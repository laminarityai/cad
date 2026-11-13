import stat
from pathlib import Path

import pytest

from cad.records.key import key_path
from cad.sandbox import stage
from cad.sandbox.outcome import Build, Built, SandboxUnavailable
from cad.variants import entry

TAG = "cad-sandbox:test"
CODE = "result = Box(1, 1, 1)\n"


def stored(root: Path) -> entry.VariantId:
    vid = entry.variant_id(CODE, TAG)
    entry.save(root, vid, CODE, Build(outcome=Built(), output=""), b"BREP")
    return vid


def test_the_first_save_creates_a_private_key_beside_the_store(tmp_path: Path) -> None:
    stored(tmp_path / "variants")
    key = tmp_path / "variants.key"
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert key.stat().st_size == 32
    assert sorted(path.name for path in tmp_path.iterdir()) == ["variants", "variants.key"]


def test_the_key_survives_a_restart_so_stored_entries_stay_open(tmp_path: Path) -> None:
    vid = stored(tmp_path / "variants")
    before = (tmp_path / "variants.key").read_bytes()
    assert entry.open_entry(tmp_path / "variants", vid, TAG).id == vid
    assert (tmp_path / "variants.key").read_bytes() == before


def test_a_key_that_others_can_read_is_refused(tmp_path: Path) -> None:
    vid = stored(tmp_path / "variants")
    (tmp_path / "variants.key").chmod(0o644)
    with pytest.raises(SandboxUnavailable, match="key is unusable") as refused:
        entry.open_entry(tmp_path / "variants", vid, TAG)
    assert str(tmp_path) not in str(refused.value)


def test_a_key_that_is_a_link_is_refused(tmp_path: Path) -> None:
    vid = stored(tmp_path / "variants")
    (tmp_path / "variants.key").rename(tmp_path / "elsewhere")
    (tmp_path / "variants.key").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(SandboxUnavailable, match="key is unusable"):
        entry.open_entry(tmp_path / "variants", vid, TAG)


def test_the_default_key_is_outside_the_store_and_the_check_mount() -> None:
    key = key_path(entry.VARIANTS_ROOT)
    assert key == Path.home() / ".cad" / "variants.key"
    assert not key.is_relative_to(entry.VARIANTS_ROOT)
    assert not key.is_relative_to(stage.check_mount().source)


def test_reading_a_variant_whose_key_is_gone_creates_no_key(tmp_path: Path) -> None:
    vid = stored(tmp_path / "variants")
    (tmp_path / "variants.key").unlink()
    with pytest.raises(entry.StaleVariant):
        entry.open_entry(tmp_path / "variants", vid, TAG)
    assert not (tmp_path / "variants.key").exists()
