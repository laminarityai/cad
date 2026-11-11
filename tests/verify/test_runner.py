import sys

import pytest

from cad.verify.__main__ import select_steps
from cad.verify.runner import run_steps
from cad.verify.steps import STEPS, Step


def python_step(name: str, code: str) -> Step:
    return Step(name, (sys.executable, "-c", code))


def test_steps_run_in_the_documented_order() -> None:
    assert [step.name for step in STEPS] == [
        "basedpyright",
        "basedpyright skills",
        "ruff check",
        "ruff format",
        "file size",
        "materials table",
        "api types",
        "web lint",
        "web test",
        "web build",
        "protocol models",
        "sandbox image",
        "pytest",
        "app",
    ]


def test_passing_steps_print_one_ok_line_each(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_steps([python_step("first", "pass"), python_step("second", "pass")])
    lines = capsys.readouterr().out.splitlines()
    assert code == 0
    assert [line.split()[0:2] for line in lines] == [["ok", "first"], ["ok", "second"]]


def test_a_step_that_asks_for_it_shows_its_output_on_success(
    capsys: pytest.CaptureFixture[str],
) -> None:
    quiet = python_step("quiet", "print('hidden detail')")
    loud = Step("loud", (sys.executable, "-c", "print('shown detail')"), show_output=True)
    assert run_steps([quiet, loud]) == 0
    out = capsys.readouterr().out
    assert "shown detail" in out
    assert "hidden detail" not in out


def test_first_failure_stops_the_run_and_shows_its_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    steps = [
        python_step("good", "pass"),
        python_step("bad", "import sys; print('boom detail'); sys.exit(3)"),
        python_step("never", "print('should not run')"),
    ]
    code = run_steps(steps)
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL bad" in out
    assert "boom detail" in out
    assert "never" not in out


def test_only_runs_the_named_steps_in_verify_order() -> None:
    chosen = select_steps(["pytest", "ruff check"])
    assert [step.name for step in chosen] == ["ruff check", "pytest"]


def test_a_bare_run_skips_the_slow_steps_that_ci_runs() -> None:
    names = [step.name for step in select_steps(None)]
    assert names == [step.name for step in STEPS if not step.slow]
    assert {"pytest", "sandbox image", "protocol models", "app"}.isdisjoint(names)


def test_all_runs_every_step() -> None:
    assert select_steps(None, every=True) == STEPS
