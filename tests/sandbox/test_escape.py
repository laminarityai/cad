"""Variant code that tries to leave the sandbox, against the real image.

The kernel's error text is the behavior under test here: it is the evidence that a flag held.
"""

import subprocess
from pathlib import Path
from unittest.mock import ANY

import pytest

from cad.sandbox import host
from cad.sandbox.image import context_tar, current_image, image_tag
from cad.sandbox.outcome import Build, BuildFailed, BuildOutcome, Built, OutOfMemory, TimedOut

FAST_WALL_SECONDS = 2


@pytest.fixture(scope="module")
def image_id() -> str:
    return current_image(image_tag(context_tar()))


def build(code: str, image_id: str, into: Path, wall_seconds: int = host.WALL_SECONDS) -> Build:
    return host.build(code, image_id, into, wall_seconds=wall_seconds)


def failed(error: str) -> BuildFailed:
    return BuildFailed.model_construct(error=error, traceback=ANY)


def exited(code: int) -> BuildFailed:
    error = f"the build process exited with code {code} before it sent a result"
    return BuildFailed(error=error, traceback="")


def stopped_build_containers() -> str:
    filters = ("--filter", f"label={host.LABEL}", "--filter", "status=exited")
    done = subprocess.run(
        ("docker", "ps", "--all", "--quiet", *filters),
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        pytest.param(
            'import socket\nsocket.create_connection(("1.1.1.1", 443), timeout=5)\n',
            failed("OSError: [Errno 101] Network is unreachable"),
            id="outbound-tcp",
        ),
        pytest.param(
            'import urllib.request\nurllib.request.urlopen("https://pypi.org")\n',
            failed(
                "urllib.error.URLError: <urlopen error [Errno -3] "
                "Temporary failure in name resolution>"
            ),
            id="dns",
        ),
        pytest.param(
            'open("/etc/x", "w")\n',
            failed("OSError: [Errno 30] Read-only file system: '/etc/x'"),
            id="write-to-root",
        ),
        pytest.param(
            f"import os\nos.listdir({str(Path.home())!r})\n",
            failed(f"FileNotFoundError: [Errno 2] No such file or directory: '{Path.home()}'"),
            id="read-host-home",
        ),
        pytest.param(
            "import os\nwhile True:\n    os.fork()\n",
            failed("BlockingIOError: [Errno 11] Resource temporarily unavailable"),
            id="fork-bomb",
        ),
        pytest.param(
            "x = bytearray(4 * 1024**3)\n", OutOfMemory(limit_mb=host.MEMORY_MB), id="4-gb"
        ),
        pytest.param(
            "x = '\udc80'\n",
            failed(
                "SyntaxError: (unicode error) 'utf-8' codec can't decode byte 0xed "
                "in position 0: invalid continuation byte"
            ),
            id="lone-surrogate",
        ),
        pytest.param("import os\nos._exit(125)\n", exited(125), id="exit-125-is-not-docker"),
        pytest.param(
            "import os, signal, time\nos.kill(os.getppid(), signal.SIGKILL)\ntime.sleep(60)\n",
            exited(137),
            id="killing-the-clock-is-not-a-timeout",
        ),
        pytest.param(
            "import os\nos.write(3, b'x' * (65 * 1024 * 1024))\nos._exit(0)\n",
            BuildFailed(error="the build sent more than 64 MiB of output", traceback=""),
            id="report-flood",
        ),
        pytest.param(
            "import resource as r\nr.setrlimit(r.RLIMIT_CPU, (1, 6))\nwhile True:\n    pass\n",
            TimedOut(limit_seconds=host.WALL_SECONDS),
            id="cpu-limit",
        ),
    ],
)
def test_escape_attempts_end_as_exact_outcomes(
    code: str, expected: BuildOutcome, image_id: str, tmp_path: Path
) -> None:
    assert build(code, image_id, tmp_path).outcome == expected
    assert list(tmp_path.iterdir()) == []


def test_the_traceback_starts_in_the_variant_code(image_id: str, tmp_path: Path) -> None:
    outcome = build("x = 1\nraise ValueError('boom')\n", image_id, tmp_path).outcome
    assert outcome == BuildFailed(
        error="ValueError: boom",
        traceback=(
            "Traceback (most recent call last):\n"
            '  File "/tmp/variant.py", line 2, in <module>\n'
            "    raise ValueError('boom')\n"
            "ValueError: boom\n"
        ),
    )


def test_the_code_runs_under_a_cpu_time_limit(image_id: str, tmp_path: Path) -> None:
    code = "import resource\nprint(resource.getrlimit(resource.RLIMIT_CPU))\n"
    assert build(code, image_id, tmp_path).output == "(60, 65)\n"


def test_an_infinite_loop_is_killed_and_its_container_removed(
    image_id: str, tmp_path: Path
) -> None:
    built = build("while True:\n    pass\n", image_id, tmp_path, FAST_WALL_SECONDS)
    assert built.outcome == TimedOut(limit_seconds=FAST_WALL_SECONDS)
    assert stopped_build_containers() == ""


def test_a_sleeping_build_is_killed_at_the_wall_clock(image_id: str, tmp_path: Path) -> None:
    built = build("import time\ntime.sleep(600)\n", image_id, tmp_path, FAST_WALL_SECONDS)
    assert built.outcome == TimedOut(limit_seconds=FAST_WALL_SECONDS)


def test_a_forked_child_never_writes_a_second_report(image_id: str, tmp_path: Path) -> None:
    code = "import os\nfrom build123d import Box\nos.fork()\nresult = Box(1, 1, 1)\n"
    assert build(code, image_id, tmp_path).outcome == Built()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["result.brep", "result.step"]
