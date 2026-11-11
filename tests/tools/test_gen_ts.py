import json
import os
import subprocess
from pathlib import Path
from typing import Any

import gen_ts
import pytest

Packages = dict[str, dict[str, Any]]

REQUIRED = {"version": "1.0.0", "resolved": "https://registry.npmjs.org/a/-/a-1.0.0.tgz"}
OTHER_PLATFORM = {"version": "2.0.0", "optional": True, "os": ["freebsd"]}


def write_packages(path: Path, packages: Packages) -> None:
    path.write_text(json.dumps({"lockfileVersion": 3, "packages": packages}))


@pytest.fixture
def web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A web directory whose install matches its lock, the way npm leaves it after `npm ci`.

    npm leaves out the root entry, and the optional packages built for another platform.
    """
    modules = tmp_path / "node_modules"
    (modules / ".bin").mkdir(parents=True)
    (modules / ".bin" / "openapi-typescript").touch()
    write_packages(
        tmp_path / "package-lock.json",
        {"": {"name": "web"}, "node_modules/a": REQUIRED, "node_modules/b": OTHER_PLATFORM},
    )
    write_packages(modules / ".package-lock.json", {"node_modules/a": REQUIRED})
    monkeypatch.setattr(gen_ts, "LOCK", tmp_path / "package-lock.json")
    monkeypatch.setattr(gen_ts, "INSTALLED", modules / ".package-lock.json")
    monkeypatch.setattr(gen_ts, "GENERATOR", modules / ".bin" / "openapi-typescript")
    monkeypatch.setattr(gen_ts, "WEB", tmp_path)
    return tmp_path


@pytest.fixture
def commands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    ran: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[None]:
        ran.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(gen_ts.subprocess, "run", fake_run)
    return ran


def test_a_matching_install_is_kept_when_a_fresh_checkout_gives_the_lock_a_newer_mtime(
    web: Path, commands: list[list[str]]
) -> None:
    lock = web / "package-lock.json"
    later = lock.stat().st_mtime + 3600
    os.utime(lock, (later, later))
    gen_ts.install_if_stale()
    assert commands == []


@pytest.mark.parametrize(
    "packages",
    [
        {"node_modules/a": {**REQUIRED, "version": "1.0.1"}},
        {"node_modules/a": REQUIRED, "node_modules/c": {"version": "3.0.0"}},
        {},
    ],
    ids=["version changed", "package added", "package removed"],
)
def test_a_changed_lock_reinstalls(web: Path, commands: list[list[str]], packages: Packages) -> None:
    write_packages(web / "package-lock.json", {"": {"name": "web"}, **packages})
    gen_ts.install_if_stale()
    assert [argv[:2] for argv in commands] == [["npm", "ci"]]
    assert commands[0][-2:] == ["--prefix", str(web)]


def test_a_missing_install_reinstalls(web: Path, commands: list[list[str]]) -> None:
    gen_ts.INSTALLED.unlink()
    gen_ts.install_if_stale()
    assert [argv[:2] for argv in commands] == [["npm", "ci"]]
