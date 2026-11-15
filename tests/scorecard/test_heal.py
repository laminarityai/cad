from pathlib import Path

import pytest

from cad.sandbox import builder, image
from cad.sandbox.builder import Artifacts, Run
from cad.sandbox.outcome import Build, Built
from cad.scorecard import score
from cad.variants import entry

TAG = "cad-sandbox:test"
OLD_TAG = "cad-sandbox:before-an-update"
CODE = "result = Box(1, 1, 1)\n"
BREP = b"CASCADE Topology V3, (c) Open Cascade\n"


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    built: list[str] = []

    def build(code: str, image_id: str, *, wall_seconds: int) -> Run:
        built.append(code)
        return Run(Artifacts(BREP, Built()), "")

    def image_tag(of: image.Image) -> str:
        return TAG

    def current_image(tag: str) -> str:
        return f"sha256:{tag}"

    monkeypatch.setattr(builder, "build", build)
    monkeypatch.setattr(image, "image_tag", image_tag)
    monkeypatch.setattr(image, "current_image", current_image)
    return built


def test_an_outdated_id_opens_its_current_build_healed_when_that_shape_was_damaged(
    tmp_path: Path, builds: list[str]
) -> None:
    old = entry.variant_id(CODE, OLD_TAG)
    entry.save(tmp_path, old, CODE, Build(outcome=Built(), output=""), b"an older shape")
    current = entry.variant_id(CODE, TAG)
    entry.save(tmp_path, current, CODE, Build(outcome=Built(), output=""), BREP)
    (tmp_path / current / entry.BREP).write_bytes(b"half a shape")
    held, rebuilt_from = score.open_or_rebuild(old, tmp_path)
    assert (held.id, held.brep, rebuilt_from, builds) == (current, BREP, old, [CODE])
