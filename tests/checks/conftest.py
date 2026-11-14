from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from cad.checks.result import BodyMaterial, CheckRun
from cad.sandbox.host import run_checks
from cad.sandbox.outcome import Built
from cad.variants.store import build_variant
from tests.support.lanes import GatedRunner


@pytest.fixture(scope="session")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("variants")


@pytest.fixture(scope="session")
def check(store: Path) -> Callable[..., CheckRun]:
    def build_and_check(code: str, material_key: str = "prusament-pla") -> CheckRun:
        """Each named body of the build is checked in the one material."""
        built = build_variant(code, store)
        bodies = built.outcome.bodies if isinstance(built.outcome, Built) else ()
        assert built.outcome == Built(bodies=bodies), built.output
        each = tuple(BodyMaterial(body=body.name, key=material_key) for body in bodies)
        return run_checks(built.variant_id, each or material_key, store)

    return build_and_check


@pytest.fixture
def runner() -> Iterator[GatedRunner]:
    made = GatedRunner()
    yield made
    made.quick.gate.set()
    made.background.gate.set()
