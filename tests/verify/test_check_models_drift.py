import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude/skills/protocol-models/scripts"


def check_models() -> Any:
    sys.path.insert(0, str(SCRIPTS))
    return importlib.import_module("check_models")


def test_a_drift_warning_names_each_model_that_covers_the_changed_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def git(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        changed = "src/cad/chat/routes.py\n" if command[1] == "diff" else ""
        return subprocess.CompletedProcess(command, 0, stdout=changed)

    covered = [
        ("JobLanes", "abc1234", ["src/cad/checks/lanes.py"]),
        ("CarryOn", "abc1234", ["src/cad/chat/routes.py"]),
        ("AutoHold", "abc1234", ["src/cad/auto/gate.py", "src/cad/chat/routes.py"]),
    ]
    script = check_models()
    monkeypatch.setattr(script, "coverage", lambda: covered)
    monkeypatch.setattr(script.subprocess, "run", git)
    script.drift()
    warnings = [line for line in capsys.readouterr().out.splitlines() if "routes.py" in line]
    assert warnings == [
        "warning: src/cad/chat/routes.py changed since sync commit abc1234; "
        "re-audit CarryOn, AutoHold against it"
    ]
