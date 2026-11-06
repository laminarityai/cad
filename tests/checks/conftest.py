from collections.abc import Callable
from pathlib import Path

import pytest

from cad.checks.result import CheckRun
from cad.sandbox.host import run_checks
from cad.sandbox.outcome import Built
from cad.variants.store import build_variant


@pytest.fixture(scope="session")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("variants")


@pytest.fixture(scope="session")
def check(store: Path) -> Callable[..., CheckRun]:
    def build_and_check(code: str, material_key: str = "prusament-pla") -> CheckRun:
        built = build_variant(code, store)
        assert built.outcome == Built(), built.output
        return run_checks(built.variant_id, material_key, store)

    return build_and_check
