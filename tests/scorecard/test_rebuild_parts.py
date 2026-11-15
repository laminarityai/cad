"""An outdated variant that read supplied parts rebuilds with the bytes it was built with,
fetched by their SHA-256, and fails plainly when they are gone (ADR-0012)."""

import hashlib
from collections.abc import Sequence
from pathlib import Path

import pytest

from cad.sandbox import builder, image
from cad.sandbox.builder import Artifacts, Run, Supplied
from cad.sandbox.outcome import Build, Built, PartPlacement, PartUse
from cad.scorecard import score
from cad.variants import entry
from cad.variants.store import RebuildFailed

TAG = "cad-sandbox:test"
OLD_TAG = "cad-sandbox:before-an-update"
CODE = "result = Box(1, 1, 1)\n"
BREP = b"CASCADE Topology V3, (c) Open Cascade\n"
WHEEL_BREP = b"CASCADE Topology V3, the wheel as it was built\n"
WHEEL = PartUse(
    part_id="part-0123456789abcdef",
    project="p-0123456789abcdef",
    brep_sha256=hashlib.sha256(WHEEL_BREP).hexdigest(),
    placements=(PartPlacement(at=(10, 0, 0)),),
)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Sequence[Supplied]]:
    builds: list[Sequence[Supplied]] = []

    def build(
        code: str, image_id: str, *, wall_seconds: int, parts: Sequence[Supplied] = ()
    ) -> Run:
        builds.append(parts)
        return Run(Artifacts(BREP, Built()), "")

    monkeypatch.setattr(builder, "build", build)
    monkeypatch.setattr(image, "image_tag", {image.BUILD: TAG}.__getitem__)
    monkeypatch.setattr(image, "current_image", "sha256:{}".format)
    return builds


def outdated(root: Path) -> entry.VariantId:
    old = entry.variant_id(CODE, OLD_TAG, (WHEEL,))
    entry.save(root, old, CODE, Build(outcome=Built(), output=""), BREP, (WHEEL,))
    return old


def test_a_rebuild_fetches_each_part_by_the_sha_it_was_built_with(
    tmp_path: Path, sent: list[Sequence[Supplied]]
) -> None:
    old = outdated(tmp_path)
    asked: list[PartUse] = []

    def fetch(use: PartUse) -> bytes:
        asked.append(use)
        return WHEEL_BREP

    held, rebuilt_from = score.open_or_rebuild(old, tmp_path, fetch)
    assert (held.id, held.parts, rebuilt_from) == (
        entry.variant_id(CODE, TAG, (WHEEL,)),
        (WHEEL,),
        old,
    )
    assert asked == [WHEEL]
    assert [[(one.use, one.brep) for one in parts] for parts in sent] == [[(WHEEL, WHEEL_BREP)]]
    again, _ = score.open_or_rebuild(old, tmp_path, lambda use: None)
    assert (again.id, len(sent)) == (held.id, 1)


@pytest.mark.parametrize("found", [None, b"CASCADE Topology V3, the wheel after an update\n"])
def test_a_rebuild_whose_part_no_longer_has_its_geometry_fails_and_builds_nothing(
    tmp_path: Path, sent: list[Sequence[Supplied]], found: bytes | None
) -> None:
    old = outdated(tmp_path)
    with pytest.raises(RebuildFailed) as raised:
        score.open_or_rebuild(old, tmp_path, lambda use: found)
    assert f"the parts it read ({WHEEL.part_id}) no longer all have the geometry" in str(
        raised.value
    )
    assert sent == []
