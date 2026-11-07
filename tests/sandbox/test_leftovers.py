import json
import os
import secrets
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from cad.sandbox import container
from cad.sandbox.image import context_tar, current_image, image_tag

WAIT_SECONDS = 90
POLL_SECONDS = 0.25


class Process(NamedTuple):
    pid: int
    argv: list[str]


@pytest.fixture(scope="module")
def image_id() -> str:
    return current_image(image_tag(context_tar()))


def wait_for[T](probe: Callable[[], T | None]) -> T:
    deadline = time.monotonic() + WAIT_SECONDS
    while (found := probe()) is None:
        assert time.monotonic() < deadline, f"gave up after {WAIT_SECONDS} s"
        time.sleep(POLL_SECONDS)
    return found


def children_of(parent: int) -> list[Process]:
    listed = subprocess.run(
        ("ps", "-A", "-o", "pid=,ppid=,command="), capture_output=True, text=True, check=True
    )
    rows = (line.split() for line in listed.stdout.splitlines())
    return [Process(int(row[0]), row[2:]) for row in rows if int(row[1]) == parent]


def status(name: str) -> str | None:
    state = container.inspect(name)
    return None if state is None else state.Status


def running_build(client: int) -> tuple[Process, Process, str] | None:
    for server in children_of(client):
        for docker in children_of(server.pid):
            if docker.argv[1:2] == ["run"]:
                name = docker.argv[docker.argv.index("--name") + 1]
                return (server, docker, name) if status(name) == "running" else None
    return None


def cad_call(tool: str, arguments: str) -> list[str]:
    return [sys.executable, "-m", "cad.server.call", tool, arguments]


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_a_server_killed_mid_build_leaves_no_container_after_the_next_start(
    image_id: str, tmp_path: Path
) -> None:
    docker_config = os.environ.get("DOCKER_CONFIG", str(Path.home() / ".docker"))
    env = {**os.environ, "HOME": str(tmp_path), "DOCKER_CONFIG": docker_config}
    code = f"# {secrets.token_hex(8)}\nwhile True:\n    pass\n"
    client = subprocess.Popen(
        cad_call("build_variant", json.dumps({"code": code})),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    name = None
    try:
        server, docker, name = wait_for(lambda: running_build(client.pid))
        os.kill(server.pid, signal.SIGTERM)
        os.kill(docker.pid, signal.SIGTERM)
        client.kill()
        client.wait()
        wait_for(lambda: True if gone(server.pid) else None)
        assert wait_for(lambda: True if status(name) == "exited" else None)
        subprocess.run(cad_call("server_info", "{}"), env=env, check=True, capture_output=True)
        assert status(name) is None
    finally:
        client.kill()
        client.wait()
        if name is not None:
            container.docker("rm", "--force", name)
