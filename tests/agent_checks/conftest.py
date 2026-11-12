import pytest

from cad.agent_checks import probes
from cad.agent_checks.gates import Shaped
from cad.agent_checks.model import CheckDraft


@pytest.fixture
def no_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """write_check without the repeat-and-turn gate, which needs Docker."""

    def passes(draft: CheckDraft, shaped: Shaped) -> None:
        return None

    monkeypatch.setattr(probes, "repeat_and_turn", passes)
