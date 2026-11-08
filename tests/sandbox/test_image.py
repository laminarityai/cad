import shutil
from pathlib import Path

import pytest

from cad.sandbox import __main__ as cli
from cad.sandbox.image import CONTEXT, SANDBOX_DIR, context_tar, current_image, image_tag
from cad.sandbox.outcome import SandboxUnavailable


def copy_of_context(into: Path) -> Path:
    for name in CONTEXT:
        shutil.copy(SANDBOX_DIR / name, into / name)
    return into


def test_the_tag_names_the_context_bytes(tmp_path: Path) -> None:
    copy = copy_of_context(tmp_path)
    assert image_tag(context_tar(copy)) == image_tag(context_tar(SANDBOX_DIR))
    with (copy / "requirements.txt").open("a") as lock:
        lock.write("\n")
    assert image_tag(context_tar(copy)) != image_tag(context_tar(SANDBOX_DIR))


def test_a_missing_image_names_the_command_that_builds_it() -> None:
    with pytest.raises(SandboxUnavailable) as raised:
        current_image("cad-sandbox:000000000000")
    assert str(raised.value) == (
        "sandbox image cad-sandbox:000000000000 is missing; run `uv run cad-sandbox build-image`"
    )


def test_build_image_is_a_no_op_when_the_image_is_current(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["build-image"]) == 0
    assert capsys.readouterr().out == f"sandbox image {image_tag(context_tar())} is current\n"


def test_build_image_says_docker_is_down_and_logs_the_cause(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent/docker.sock")
    assert cli.main(["build-image"]) == 1
    assert capsys.readouterr().out == "docker is not reachable\n"
    assert "unix:///nonexistent/docker.sock" in caplog.text


def test_build_image_says_so_when_docker_is_not_installed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert cli.main(["build-image"]) == 1
    assert capsys.readouterr().out == "docker is not installed: no `docker` command on PATH\n"
