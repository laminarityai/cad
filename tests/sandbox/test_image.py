import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from cad.checks.report import DEPENDENCIES, specs
from cad.sandbox import __main__ as cli
from cad.sandbox import image
from cad.sandbox.host import run_checks
from cad.sandbox.image import ANALYSIS, BUILD, IMAGES, Image, current_image, image_tag
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants.store import build_variant

PLATE = (Path(__file__).parent / "parts/plate.py").read_text()


def copy_of(source: Image, into: Path) -> Image:
    for name in source.context:
        shutil.copy(source.directory / name, into / name)
    return replace(source, directory=into)


def appended_to(source: Image, name: str, into: Path) -> Image:
    copy = copy_of(source, into)
    with (copy.directory / name).open("a") as file:
        file.write("\n")
    return copy


def test_the_tag_names_the_context_bytes(tmp_path: Path) -> None:
    assert image_tag(copy_of(BUILD, tmp_path)) == image_tag(BUILD)
    assert image_tag(appended_to(BUILD, "requirements.txt", tmp_path)) != image_tag(BUILD)


def test_a_new_build_image_gives_a_new_analysis_tag(tmp_path: Path) -> None:
    edited = appended_to(BUILD, "requirements.txt", tmp_path)
    assert image_tag(replace(ANALYSIS, base=edited)) != image_tag(ANALYSIS)


def test_a_new_analysis_context_changes_every_check_version_and_no_variant_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "variants"
    before = build_variant(PLATE, store).variant_id
    edited = appended_to(ANALYSIS, "Dockerfile", tmp_path)
    monkeypatch.setattr(image, "ANALYSIS", edited)
    assert build_variant(PLATE, store).variant_id == before
    assert run_checks(before, "prusament-pla", store).variant_id == before
    old = specs(DEPENDENCIES, image_tag(ANALYSIS))
    new = specs(DEPENDENCIES, image_tag(edited))
    assert all(a.version != b.version for a, b in zip(old, new, strict=True))


def test_a_missing_image_names_the_command_that_builds_it() -> None:
    with pytest.raises(SandboxUnavailable) as raised:
        current_image("cad-sandbox:000000000000")
    assert str(raised.value) == (
        "sandbox image cad-sandbox:000000000000 is missing; run `uv run cad-sandbox build-image`"
    )


def test_build_image_is_a_no_op_when_both_images_are_current(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["build-image"]) == 0
    expected = "".join(f"sandbox image {image_tag(each)} is current\n" for each in IMAGES)
    assert capsys.readouterr().out == expected


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
