import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from cad.operations import registry
from cad.operations.server import GitState
from cad.server import probe

WRONG_SHA = "0" * 40


def reporting(info: dict[str, Any]) -> Any:
    async def fake_call(
        name: str, arguments: dict[str, Any], url: str | None = None, token: str | None = None
    ) -> dict[str, Any]:
        return {"isError": False, "structuredContent": info}

    return fake_call


@contextmanager
def no_http_server() -> Generator[tuple[str, str]]:
    yield "http://127.0.0.1:1/mcp", "token"


@pytest.fixture(autouse=True)
def stays_off_http(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if "real_server" not in request.node.name:
        monkeypatch.setattr(probe, "hosted", no_http_server)


def head_of_this_repo() -> str:
    return subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=probe.REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.mark.usefixtures("alone_removing_orphans")
def test_real_server_passes_and_prints_the_sha(capsys: pytest.CaptureFixture[str]) -> None:
    assert probe.main() == 0
    out = capsys.readouterr().out
    assert f"server_info over stdio sha {head_of_this_repo()}" in out
    assert f"server_info over http sha {head_of_this_repo()}" in out


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


def test_an_http_server_that_will_not_start_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def broken() -> Generator[tuple[str, str]]:
        raise RuntimeError("cad-http exited with 1")
        yield "", ""

    monkeypatch.setattr(probe, "call_tool", reporting({"sha": head_of_this_repo(), "dirty": False}))
    monkeypatch.setattr(probe, "hosted", broken)
    assert probe.main() == 1
