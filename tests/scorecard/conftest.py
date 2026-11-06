from collections.abc import Callable
from pathlib import Path

import pytest

from cad.sandbox.outcome import Built
from cad.variants.store import build_variant


@pytest.fixture(scope="session")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("variants")


@pytest.fixture(scope="session")
def built(store: Path) -> Callable[[str], str]:
    def build(code: str) -> str:
        result = build_variant(code, store)
        assert result.outcome == Built(), result.output
        return result.variant_id

    return build
