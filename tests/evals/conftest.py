from pathlib import Path

import pytest

from cad.sandbox.outcome import Build, Built
from cad.variants import entry
from tests.support.cards import BREP, STEP, VARIANT_ID


@pytest.fixture
def store(tmp_path: Path) -> Path:
    root = tmp_path / "store"
    root.mkdir()
    entry.save(
        root, entry.VariantId(VARIANT_ID), "x = 1\n", Build(outcome=Built(), output=""), BREP
    )
    (root / VARIANT_ID / entry.STEP).write_bytes(STEP)
    return root
