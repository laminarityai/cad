"""The bake-off reference parts build, and the store keeps one variant per code."""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import pytest

from cad.sandbox.outcome import Built, TimedOut
from cad.variants.store import BuildResult, build_variant

PARTS = {path.stem: path.read_text() for path in (Path(__file__).parent / "parts").glob("*.py")}


@pytest.fixture(scope="module")
def built_parts(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Mapping[str, BuildResult]]:
    root = tmp_path_factory.mktemp("variants")
    with ThreadPoolExecutor(4) as pool:
        results = pool.map(partial(build_variant, root=root), PARTS.values())
        return root, dict(zip(PARTS, results, strict=True))


def test_there_are_ten_reference_parts() -> None:
    assert len(PARTS) == 10


@pytest.mark.parametrize("part", sorted(PARTS))
def test_reference_part_builds_and_stores_its_files(
    part: str, built_parts: tuple[Path, Mapping[str, BuildResult]]
) -> None:
    root, results = built_parts
    result = results[part]
    assert result.outcome == Built(), result.output
    stored = root / result.variant_id
    assert sorted(path.name for path in stored.iterdir()) == [
        "build.json",
        "code.py",
        "result.brep",
        "result.step",
    ]
    assert (stored / "code.py").read_text() == PARTS[part]


def test_a_timed_out_build_is_not_stored(tmp_path: Path) -> None:
    result = build_variant("while True:\n    pass\n", tmp_path, wall_seconds=2)
    assert result.outcome == TimedOut(limit_seconds=2)
    assert list(tmp_path.iterdir()) == []


def test_a_changed_comment_is_a_new_variant(tmp_path: Path) -> None:
    first = build_variant("x = 1\n", tmp_path)
    second = build_variant("x = 1\n# again\n", tmp_path)
    assert first.variant_id != second.variant_id
