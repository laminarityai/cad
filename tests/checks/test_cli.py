from pathlib import Path

import pytest

from cad.checks.result import CheckRun, Verdict
from cad.sandbox import __main__ as cli
from cad.sandbox import stage
from cad.sandbox.image import context_tar, image_tag
from cad.sandbox.outcome import Build, Built, NoResult
from cad.variants import entry
from cad.variants.store import build_variant

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
OLD_ID = "fe250eb62250be75"


def test_run_checks_prints_the_check_run_as_json_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built = build_variant(PLATE, tmp_path)
    assert cli.main(["run-checks", built.variant_id, "prusament-pla", "--root", str(tmp_path)]) == 0
    run = CheckRun.model_validate_json(capsys.readouterr().out)
    assert run.variant_id == built.variant_id
    assert [result.verdict for result in run.results] == [Verdict.PASS] * 3


def test_a_failing_check_is_still_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built = build_variant(
        PLATE + "from build123d import Shell\nresult = Shell(result.faces()[:-1])\n", tmp_path
    )
    assert cli.main(["run-checks", built.variant_id, "prusament-pla", "--root", str(tmp_path)]) == 0
    run = CheckRun.model_validate_json(capsys.readouterr().out)
    assert run.result("closed_solid").verdict == Verdict.FAIL


def test_a_stale_variant_is_one_line_and_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / OLD_ID).mkdir()
    (tmp_path / OLD_ID / "code.py").write_text("result = 1\n")
    assert cli.main(["run-checks", OLD_ID, "prusament-pla", "--root", str(tmp_path)]) == 1
    assert capsys.readouterr().out == (
        f"StaleVariant: variant {OLD_ID} was not stored by this version of the sandbox; "
        "build its code again\n"
    )


def test_an_unknown_id_is_one_line_and_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["run-checks", "../x", "prusament-pla", "--root", str(tmp_path)]) == 1
    assert capsys.readouterr().out == (
        "UnknownVariant: a variant id is 16 lowercase hex digits, not '../x'\n"
    )


def test_a_variant_that_did_not_build_is_not_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = "x = 1\n"
    vid = entry.variant_id(code, image_tag(context_tar()))
    entry.save(tmp_path, vid, code, Build(outcome=NoResult(reason="r"), output=""), None)
    assert cli.main(["run-checks", vid, "prusament-pla", "--root", str(tmp_path)]) == 1
    assert capsys.readouterr().out.startswith(f"NotBuilt: variant {vid} has no shape")


def test_a_stage_root_that_cannot_be_written_is_one_line_and_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code = "x = 1\n"
    vid = entry.variant_id(code, image_tag(context_tar()))
    entry.save(tmp_path, vid, code, Build(outcome=Built(), output=""), b"BREP")
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o555)
    monkeypatch.setattr(stage, "STAGE_ROOT", locked / "stage")
    try:
        assert cli.main(["run-checks", vid, "prusament-pla", "--root", str(tmp_path)]) == 1
    finally:
        locked.chmod(0o755)
    assert capsys.readouterr().out.startswith(f"cannot stage the check sources in {locked}")
