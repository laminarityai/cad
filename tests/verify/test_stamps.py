import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

from cad.verify.__main__ import stamps_for
from cad.verify.runner import run_steps
from cad.verify.stamps import Stamps
from cad.verify.steps import ROOT, STEPS, Step


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("one\n")
    (root / "README").write_text("outside\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    return root


def counting(root: Path, *, fails: bool = False) -> Step:
    """A step that reads src/ and appends a line to `runs` each time it really runs."""
    code = f"open({str(root / 'runs')!r}, 'a').write('ran\\n'); raise SystemExit({int(fails)})"
    return Step("counting", (sys.executable, "-c", code), inputs=("src/*",))


def run(root: Path, step: Step) -> tuple[int, str]:
    code = run_steps([step], Stamps.scan(root, root.parent / "cache"))
    runs = root / "runs"
    return code, runs.read_text() if runs.exists() else ""


def test_a_passed_step_is_skipped_and_says_so(
    checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    step = counting(checkout)
    assert run(checkout, step) == (0, "ran\n")
    capsys.readouterr()
    assert run(checkout, step) == (0, "ran\n")
    assert capsys.readouterr().out.startswith("skip counting (passed before on these inputs")


def test_an_edited_input_reruns_the_step(checkout: Path) -> None:
    step = counting(checkout)
    run(checkout, step)
    (checkout / "src" / "a.py").write_text("two\n")
    assert run(checkout, step) == (0, "ran\n" * 2)


def test_a_new_untracked_input_reruns_the_step(checkout: Path) -> None:
    step = counting(checkout)
    run(checkout, step)
    (checkout / "src" / "b.py").write_text("new\n")
    assert run(checkout, step) == (0, "ran\n" * 2)


def test_an_edit_outside_the_inputs_keeps_the_skip(checkout: Path) -> None:
    step = counting(checkout)
    run(checkout, step)
    (checkout / "README").write_text("changed\n")
    assert run(checkout, step) == (0, "ran\n")


def test_a_failed_step_leaves_no_stamp(checkout: Path) -> None:
    run(checkout, counting(checkout))
    assert run(checkout, counting(checkout, fails=True))[1] == "ran\n" * 2
    assert not list((checkout.parent / "cache").rglob("*.stamp"))
    assert run(checkout, counting(checkout, fails=True)) == (1, "ran\n" * 3)


def test_a_step_without_inputs_always_runs(checkout: Path) -> None:
    step = counting(checkout)
    bare = Step(step.name, step.argv)
    run(checkout, bare)
    assert run(checkout, bare) == (0, "ran\n" * 2)


def test_a_step_is_not_skipped_while_its_output_is_missing(checkout: Path) -> None:
    step = counting(checkout)
    made = Step(step.name, step.argv, inputs=step.inputs, outputs=("dist/index.html",))
    run(checkout, made)
    assert run(checkout, made) == (0, "ran\n" * 2)
    (checkout / "dist").mkdir()
    (checkout / "dist" / "index.html").write_text("built\n")
    assert run(checkout, made) == (0, "ran\n" * 2)


@pytest.mark.parametrize(("environ", "no_cache"), [({"CI": "1"}, False), ({}, True)])
def test_ci_and_no_cache_never_read_or_write_stamps(
    tmp_path: Path, environ: dict[str, str], no_cache: bool
) -> None:
    assert stamps_for(no_cache=no_cache, environ=environ, cache=tmp_path) is None
    assert isinstance(stamps_for(no_cache=False, environ={}, cache=tmp_path), Stamps)


def test_every_input_pattern_matches_a_file_in_this_checkout() -> None:
    """A mistyped pattern matches nothing, so the step would not rerun when that file changes. A
    bare suffix such as `*.pyi` may wait for its first file."""
    files = Stamps.scan(ROOT, ROOT / "unused").files
    for step in STEPS:
        for pattern in step.inputs:
            if pattern.startswith("*.") and "/" not in pattern:
                continue
            assert any(fnmatchcase(name, pattern) for name in files), (step.name, pattern)


def test_without_stamps_a_step_that_passed_runs_again(checkout: Path) -> None:
    step = counting(checkout)
    run(checkout, step)
    assert run_steps([step], None) == 0
    assert (checkout / "runs").read_text() == "ran\n" * 2
