"""Issue #6: a variant could forge its build report so result.step differed from what the checks
measure, and pre-fix store entries stayed addressable by id."""

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from cad.checks.result import CheckRun, StepMissing, StepStored, Verdict
from cad.sandbox import container
from cad.sandbox.container import Job, ReadOnlyMount
from cad.sandbox.host import run_checks
from cad.sandbox.image import ANALYSIS, current_image, image_tag
from cad.sandbox.outcome import Built
from cad.variants.entry import StaleVariant
from cad.variants.store import build_variant

NO_DOCKER = "unix:///nonexistent/docker.sock"

FORGE_REPORT = """import base64, json, os
report = {{"kind": "built", "brep": base64.b64encode({brep}).decode(){extra}}}
os.write(3, json.dumps(report).encode())
os._exit(0)
"""
FORGED_STEP_REPORT = FORGE_REPORT.format(
    brep='b"FORGED-BREP"', extra=', "step": base64.b64encode(b"FORGED-" + b"STEP").decode()'
)
FORGED_STEP_MARKER = b"FORGED-STEP"
FORGE_PATCH = """import build123d
from build123d import Box
_real = build123d.export_step
def _swap(shape, file_path, *, timestamp):
    return _real(Box(1, 1, 1), file_path, timestamp=timestamp)
build123d.export_step = _swap
result = Box(20, 20, 20)
"""
STEP_PROBE = """import json, os
saved = os.dup(1)
os.dup2(2, 1)
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader

reader = STEPControl_Reader()
assert reader.ReadFile("/entry/result.step") == IFSelect_RetDone
reader.TransferRoots()
shape = reader.OneShape()
props = GProp_GProps()
BRepGProp.VolumeProperties_s(shape, props)
box = Bnd_Box()
BRepBndLib.Add_s(shape, box)
low, high = box.CornerMin(), box.CornerMax()
extent = [high.X() - low.X(), high.Y() - low.Y(), high.Z() - low.Z()]
os.write(saved, json.dumps({"volume": props.Mass(), "extent": extent}).encode())
"""


def stored_files(root: Path, variant_id: str) -> list[str]:
    return sorted(path.name for path in (root / variant_id).iterdir())


def read_step_back(step: Path, workdir: Path) -> dict[str, object]:
    shared = workdir / "entry"
    shared.mkdir()
    shared.chmod(0o755)
    shutil.copy(step, shared / "result.step")
    (shared / "result.step").chmod(0o644)
    image = current_image(image_tag(ANALYSIS))
    job = Job(
        "check", image, ("python", "-I", "-c", STEP_PROBE), b"", (ReadOnlyMount(shared, "/entry"),)
    )
    ran = container.run(job)
    assert ran.state.ExitCode == 0, ran.attended.output
    assert isinstance(ran.attended.report, bytes)
    return json.loads(ran.attended.report)


def test_a_step_in_the_report_is_discarded(tmp_path: Path) -> None:
    built = build_variant(FORGED_STEP_REPORT, tmp_path)
    assert built.outcome == Built(), built.output
    assert stored_files(tmp_path, built.variant_id) == [
        "build.json",
        "build.mac",
        "code.py",
        "result.brep",
    ]
    for path in tmp_path.rglob("*"):
        assert path.is_dir() or FORGED_STEP_MARKER not in path.read_bytes(), path


@pytest.mark.parametrize(
    "brep", ['b"FORGED-BREP"', "os.urandom(4096)"], ids=["forged-bytes", "random-bytes"]
)
def test_a_forged_brep_is_checked_and_no_step_is_invented_from_it(
    brep: str, tmp_path: Path
) -> None:
    built = build_variant(FORGE_REPORT.format(brep=brep, extra=""), tmp_path)
    assert built.outcome == Built(), built.output
    run = run_checks(built.variant_id, "prusament-pla", tmp_path)
    closed = run.result("closed_solid")
    assert closed.verdict == Verdict.FAIL
    assert closed.reason.startswith("the BREP could not be read")
    unmeasured = [run.result(id).verdict for id in ("interference", "mass", "extents")]
    assert unmeasured == [Verdict.UNKNOWN] * 3
    assert run.step == StepMissing(reason="no STEP was derived, because the BREP could not be read")
    assert "result.step" not in stored_files(tmp_path, built.variant_id)
    again = run_checks(built.variant_id, "prusament-pla", tmp_path)
    assert again.model_dump_json() == run.model_dump_json()


def test_patching_the_step_exporter_changes_nothing_that_is_stored(tmp_path: Path) -> None:
    built = build_variant(FORGE_PATCH, tmp_path)
    assert built.outcome == Built(), built.output
    assert stored_files(tmp_path, built.variant_id) == [
        "build.json",
        "build.mac",
        "code.py",
        "result.brep",
    ]
    run = run_checks(built.variant_id, "prusament-pla", tmp_path)
    assert run.result("mass").number("volume", "mm^3") == pytest.approx(8000, rel=1e-6)
    step = tmp_path / built.variant_id / "result.step"
    assert run.step == StepStored(sha256=hashlib.sha256(step.read_bytes()).hexdigest())
    read_back = read_step_back(step, tmp_path)
    assert read_back["volume"] == pytest.approx(8000, rel=1e-6)
    assert read_back["extent"] == pytest.approx([20, 20, 20], abs=0.01)


def test_a_step_is_stored_for_a_real_part_and_matches_what_was_measured(
    check: Callable[..., CheckRun], store: Path, tmp_path: Path
) -> None:
    code = "from build123d import Box\nresult = Box(10, 20, 30)\n"
    run = check(code)
    read_back = read_step_back(store / run.variant_id / "result.step", tmp_path)
    assert read_back["volume"] == pytest.approx(6000, rel=1e-6)
    assert read_back["extent"] == pytest.approx([10, 20, 30], abs=0.01)


def test_a_pre_fix_directory_named_by_its_old_id_is_refused_without_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    old = tmp_path / "cb1330bebb5df2d7"
    old.mkdir()
    (old / "code.py").write_text(FORGE_PATCH)
    (old / "build.json").write_text('{"outcome": {"kind": "built"}, "output": ""}')
    (old / "result.brep").write_bytes(b"CASCADE")
    (old / "result.step").write_bytes(b"FORGED STEP")
    with pytest.raises(StaleVariant, match="variant cb1330bebb5df2d7 was not stored by this"):
        run_checks("cb1330bebb5df2d7", "prusament-pla", tmp_path)
