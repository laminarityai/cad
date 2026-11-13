from pathlib import Path

import pytest

from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built, SandboxUnavailable
from cad.variants import entry, store

CODE = "from build123d import Box\nresult = Box(1, 1, 1)\n"


def fill(root: Path, size: int) -> None:
    (root / "0123456789abcdef").mkdir(parents=True)
    (root / "0123456789abcdef" / "result.brep").write_bytes(b"\0" * size)


def test_a_store_at_its_limit_refuses_new_code_before_it_builds(tmp_path: Path) -> None:
    fill(tmp_path, 1024)
    with pytest.raises(SandboxUnavailable, match=r"full \(1024 of 1024 bytes\)"):
        store.build_variant(CODE, tmp_path, cap_bytes=1024)
    assert [path.name for path in tmp_path.iterdir()] == ["0123456789abcdef"]


def test_a_store_at_its_limit_still_returns_code_it_already_built(tmp_path: Path) -> None:
    vid = entry.variant_id(CODE, image_tag(BUILD))
    entry.save(tmp_path, vid, CODE, Build(outcome=Built(), output=""), b"BREP")
    fill(tmp_path, 1024)
    again = store.build_variant(CODE, tmp_path, cap_bytes=1024)
    assert (again.variant_id, again.outcome) == (vid, Built())
