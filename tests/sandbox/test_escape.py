import subprocess
from pathlib import Path
from unittest.mock import ANY

import pytest

from cad.sandbox import container, host
from cad.sandbox.image import context_tar, current_image, image_tag
from cad.sandbox.outcome import BuildFailed, BuildOutcome, Built, Failure, OutOfMemory, TimedOut

FAST_WALL_SECONDS = 2


@pytest.fixture(scope="module")
def image_id() -> str:
    return current_image(image_tag(context_tar()))


def outcome(
    code: str, image_id: str, wall_seconds: int = container.WALL_SECONDS
) -> Built | Failure:
    verdict = host.build(code, image_id, wall_seconds=wall_seconds).verdict
    return Built() if isinstance(verdict, host.Artifacts) else verdict


def failed(error: str) -> BuildFailed:
    return BuildFailed.model_construct(error=error, traceback=ANY)


def exited(code: int) -> BuildFailed:
    error = f"the build process exited with code {code} before it sent a result"
    return BuildFailed(error=error, traceback="")


def stopped_build_containers() -> str:
    filters = ("--filter", f"label={container.label('build')}", "--filter", "status=exited")
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
            "x = bytearray(4 * 1024**3)\n", OutOfMemory(limit_mb=container.MEMORY_MB), id="4-gb"
        ),
        pytest.param(
            "x = '\udc80'\n",
            failed(
                "SyntaxError: (unicode error) 'utf-8' codec can't decode byte 0xed "
                "in position 0: invalid continuation byte"
            ),
            id="lone-surrogate-in-code",
        ),
        pytest.param(
            'raise ValueError("bad \\ud800 char")\n',
            failed("ValueError: bad ? char"),
            id="lone-surrogate-in-error",
        ),
        pytest.param(
            'try:\n    compile("(", "x", "exec")\n'
            'except SyntaxError as error:\n    error.add_note("a note")\n    raise\n',
            failed("SyntaxError: '(' was never closed"),
            id="syntax-error-with-a-note",
        ),
        pytest.param("import os\nos._exit(125)\n", exited(125), id="exit-125-is-not-docker"),
        pytest.param("import os\nos._exit(152)\n", exited(152), id="exit-152-is-not-a-timeout"),
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
    ],
)
def test_escape_attempts_end_as_exact_outcomes(
    code: str, expected: BuildOutcome, image_id: str
) -> None:
    assert outcome(code, image_id) == expected


def test_the_traceback_starts_in_the_variant_code(image_id: str) -> None:
    assert outcome("x = 1\nraise ValueError('boom')\n", image_id) == BuildFailed(
        error="ValueError: boom",
        traceback=(
            "Traceback (most recent call last):\n"
            '  File "/tmp/variant.py", line 2, in <module>\n'
            "    raise ValueError('boom')\n"
            "ValueError: boom\n"
        ),
    )


def test_the_cpu_time_limit_allows_every_cpu_for_the_whole_wall_clock(image_id: str) -> None:
    code = "import resource\nprint(resource.getrlimit(resource.RLIMIT_CPU))\n"
    assert host.build(code, image_id).output == "(120, 125)\n"


def test_an_infinite_loop_is_killed_and_its_container_removed(image_id: str) -> None:
    assert outcome("while True:\n    pass\n", image_id, FAST_WALL_SECONDS) == TimedOut(
        limit_seconds=FAST_WALL_SECONDS
    )
    assert stopped_build_containers() == ""


def test_a_sleeping_build_is_killed_at_the_wall_clock(image_id: str) -> None:
    assert outcome("import time\ntime.sleep(600)\n", image_id, FAST_WALL_SECONDS) == TimedOut(
        limit_seconds=FAST_WALL_SECONDS
    )


def test_a_forked_child_never_writes_a_second_report(image_id: str) -> None:
    code = "import os\nfrom build123d import Box\nos.fork()\nresult = Box(1, 1, 1)\n"
    assert outcome(code, image_id) == Built()
