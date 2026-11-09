from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from cad.sandbox import stage
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard import score
from cad.tables.materials import load_materials
from cad.variants import entry

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()

type Build = Callable[[str], str]


def refusal_of(variant_id: str, store: Path) -> str:
    with pytest.raises(SandboxUnavailable) as refused:
        score.score_variant(variant_id, "prusament-pla", store)
    return str(refused.value)


@pytest.fixture
def unreadable_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    table = tmp_path / "materials.yaml"
    table.write_text("materials: []\n")
    table.chmod(0o000)
    monkeypatch.setattr(load_materials, "__defaults__", (table,))
    yield table
    table.chmod(0o644)


def test_a_step_that_cannot_be_stored_names_the_variant_and_the_kind_and_no_host_path(
    built: Build, store: Path, caplog: pytest.LogCaptureFixture
) -> None:
    variant_id = built(PLATE + "# step store fails\n")
    step = store / variant_id / entry.STEP
    step.unlink(missing_ok=True)
    step.mkdir()
    message = refusal_of(variant_id, store)
    step.rmdir()
    assert variant_id in message
    assert "IsADirectoryError" in message
    assert str(store) not in message
    assert str(step) in caplog.text


def test_a_stage_that_cannot_be_written_names_the_variant_and_the_kind_and_no_host_path(
    built: Build,
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    variant_id = built(PLATE + "# stage fails\n")  # no earlier test in the session scored it
    root = tmp_path / "stage"
    root.mkdir(mode=0o555)
    monkeypatch.setattr(stage, "STAGE_ROOT", root)
    message = refusal_of(variant_id, store)
    root.chmod(0o755)
    assert variant_id in message
    assert "PermissionError" in message
    assert str(tmp_path) not in message
    assert str(root) in caplog.text


def test_an_unreadable_materials_table_names_the_kind_and_no_host_path(
    built: Build, store: Path, unreadable_table: Path, caplog: pytest.LogCaptureFixture
) -> None:
    message = refusal_of(built(PLATE), store)
    assert "materials table" in message
    assert "PermissionError" in message
    assert str(unreadable_table.parent) not in message
    assert str(unreadable_table) in caplog.text
