import subprocess
from pathlib import Path
from typing import Any

import pytest

from cad.operations import registry
from cad.operations.server import GitState
from cad.server import probe

WRONG_SHA = "0" * 40


def reporting(info: dict[str, Any]) -> Any:
    async def fake_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"isError": False, "structuredContent": info}

    return fake_call


def head_of_this_repo() -> str:
    return subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=probe.REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_real_server_passes_and_prints_the_sha(capsys: pytest.CaptureFixture[str]) -> None:
    assert probe.main() == 0
    assert f"sha {head_of_this_repo()}" in capsys.readouterr().out


def test_wrong_sha_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe, "call_tool", reporting({"sha": WRONG_SHA, "dirty": False}))
    assert probe.main() == 1


def test_wrong_sha_fails_even_when_the_servers_own_git_lookup_agrees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def lying_git_state(root: Path) -> GitState:
        return GitState(WRONG_SHA, False)

    monkeypatch.setattr(registry, "git_state", lying_git_state)
    monkeypatch.setattr(probe, "call_tool", reporting({"sha": WRONG_SHA, "dirty": False}))
    assert probe.main() == 1


def test_dirty_is_reported_and_does_not_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    info = {"sha": head_of_this_repo(), "dirty": True}
    monkeypatch.setattr(probe, "call_tool", reporting(info))
    assert probe.main() == 0
    assert "dirty=True" in capsys.readouterr().out


def test_unknown_on_both_sides_fails_when_git_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(probe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(probe, "call_tool", reporting({"sha": "unknown", "dirty": False}))
    assert probe.main() == 1


def test_server_reporting_unknown_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe, "call_tool", reporting({"sha": "unknown", "dirty": False}))
    assert probe.main() == 1
