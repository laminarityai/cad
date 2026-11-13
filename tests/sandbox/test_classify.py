import json
import os
from base64 import b64encode
from pathlib import Path

import pytest

from cad.sandbox.container import (
    Attended,
    ContainerState,
    Job,
    TooMuchOutput,
    run_argv,
)
from cad.sandbox.host import TEXT_CAP, Artifacts, build_job, classify
from cad.sandbox.outcome import BuildFailed, Failure, NoResult, OutOfMemory, TimedOut

OWN_LIMITS = Job("build", "sha256:sandbox", (), b"", wall_seconds=60, memory_mb=1536)
CONTRACT = "assign the final shape to `result`"
MALFORMED = BuildFailed(error="the build sent a malformed result", traceback="")


def built_report(brep: bytes = b"brep bytes", **extra: str) -> bytes:
    return json.dumps({"kind": "built", "brep": b64encode(brep).decode(), **extra}).encode()


def failed_report(error: str = "ValueError: boom", traceback: str = "Traceback ...") -> bytes:
    return json.dumps({"kind": "build_failed", "error": error, "traceback": traceback}).encode()


def seen(report: bytes | TooMuchOutput, *, killed: bool = False) -> Attended:
    return Attended(killed_at_deadline=killed, report=report, output="")


def state(exit_code: int, *, oom: bool = False) -> ContainerState:
    return ContainerState(Status="exited", ExitCode=exit_code, OOMKilled=oom, Error="")


def exited_without_report(code: int) -> BuildFailed:
    return BuildFailed(
        error=f"the build process exited with code {code} before it sent a result", traceback=""
    )


@pytest.mark.parametrize(
    ("attended", "container", "expected"),
    [
        pytest.param(
            seen(built_report(), killed=True), state(0),
            TimedOut(limit_seconds=OWN_LIMITS.wall_seconds),
            id="kill",
        ),
        pytest.param(seen(built_report()), state(0), Artifacts(b"brep bytes"), id="built"),
        pytest.param(
            seen(built_report(step=b64encode(b"FORGED-STEP").decode())), state(0),
            Artifacts(b"brep bytes"), id="a-step-in-the-report-is-discarded",
        ),
        pytest.param(
            seen(built_report()), state(0, oom=True), Artifacts(b"brep bytes"),
            id="report-beats-a-child-oom",
        ),
        pytest.param(
            seen(failed_report()), state(0),
            BuildFailed(error="ValueError: boom", traceback="Traceback ..."), id="failed",
        ),
        pytest.param(
            seen(b'{"kind": "no_result"}'), state(0),
            NoResult(reason=f"the code never assigned `result`; {CONTRACT}"), id="no-result",
        ),
        pytest.param(
            seen(b'{"kind": "not_a_shape", "found": "int"}'), state(0),
            NoResult(reason=f"`result` is of type int, not a build123d Shape; {CONTRACT}"),
            id="not-a-shape",
        ),
        pytest.param(
            seen(b""), state(137, oom=True), OutOfMemory(limit_mb=1536), id="oom"
        ),
        pytest.param(seen(b""), state(152), exited_without_report(152), id="152-is-not-timeout"),
        pytest.param(seen(b""), state(137), exited_without_report(137), id="137-is-not-timeout"),
        pytest.param(seen(built_report()), state(1), exited_without_report(1), id="nonzero-exit"),
        pytest.param(seen(b""), state(0), exited_without_report(0), id="exit-0-silent"),
        pytest.param(
            seen(TooMuchOutput()), state(0),
            BuildFailed(error="the build sent more than 64 MiB of output", traceback=""),
            id="over-the-cap",
        ),
        pytest.param(seen(b'{"kind": "won"}'), state(0), MALFORMED, id="bad-tag"),
        pytest.param(
            seen(b'{"kind": "build_failed", "error": 1, "traceback": ""}'), state(0), MALFORMED,
            id="wrong-type",
        ),
        pytest.param(seen(failed_report() + b"{}"), state(0), MALFORMED, id="extra-json"),
        pytest.param(seen(b"[]"), state(0), MALFORMED, id="not-an-object"),
        pytest.param(
            seen(b'{"kind": "built", "brep": "@@"}'), state(0), MALFORMED,
            id="bad-base64",
        ),
        pytest.param(
            seen(b'{"kind": "built", "brep": "caf\\u00e9"}'), state(0), MALFORMED,
            id="non-ascii-base64",
        ),
    ],
)  # fmt: skip
def test_classify(
    attended: Attended, container: ContainerState, expected: Artifacts | Failure
) -> None:
    assert classify(attended, container, OWN_LIMITS) == expected


def test_report_strings_keep_the_error_head_and_the_traceback_tail() -> None:
    error = "ValueError: " + "e" * TEXT_CAP
    traceback = "t" * TEXT_CAP + "ValueError: last line"
    verdict = classify(seen(failed_report(error=error, traceback=traceback)), state(0), OWN_LIMITS)
    assert verdict == BuildFailed(error=error[:TEXT_CAP], traceback=traceback[-TEXT_CAP:])


def test_the_container_runs_locked_down() -> None:
    runner = (Path(__file__).parents[2] / "src/cad/sandbox/runner.py").read_text()
    job = build_job("x = 1\n", "sha256:abc", OWN_LIMITS.wall_seconds)
    assert job == Job("build", "sha256:abc", ("python", "-I", "-c", runner, "120"), b"x = 1\n")
    assert run_argv("cad-build-1", job) == (
        "docker", "run", "--name", "cad-build-1", "--label", "cad.sandbox=build",
        "--label", f"cad.owner-pid={os.getpid()}",
        "--interactive", "--sig-proxy=false", "--init", "--pull", "never",
        "--log-driver", "none", "--network", "none",
        "--memory", "2048m", "--memory-swap", "2048m",
        "--pids-limit", "128", "--cpus", "2",
        "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534", "--env", "HOME=/tmp", "--workdir", "/tmp",
        "sha256:abc",
        "timeout", "--signal", "KILL", "65",
        "python", "-I", "-c", runner, "120",
    )  # fmt: skip
