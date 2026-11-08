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


def wait_until(condition: Callable[[], bool]) -> None:
    wait_for(lambda: True if condition() else None)


def wait_until_exited(name: str) -> None:
    wait_until(lambda: status(name) == "exited")


def running_build(client: int) -> tuple[Process, Process, str] | None:
    for server in children_of(client):
        for docker in children_of(server.pid):
            if docker.argv[1:2] == ["run"]:
                name = docker.argv[docker.argv.index("--name") + 1]
                return (server, docker, name) if status(name) == "running" else None
    return None


def cad_call(tool: str, arguments: str) -> list[str]:
    return [sys.executable, "-m", "cad.server.call", tool, arguments]


def start(image_id: str, owner: int | str, *command: str) -> str:
    name = f"cad-build-{secrets.token_hex(8)}"
    subprocess.run(
        ("docker", "run", "--detach", "--name", name, "--label", container.label("build"),
         "--label", f"{container.OWNER}={owner}", "--pull", "never", "--network", "none",
         image_id, *command),
        capture_output=True, check=True,
    )  # fmt: skip
    return name


def dead_pid() -> int:
    ended = subprocess.run(
        (sys.executable, "-c", "import os; print(os.getpid())"),
        capture_output=True,
        text=True,
        check=True,
    )
    return int(ended.stdout)


def test_only_exited_containers_whose_owner_is_gone_are_removed(image_id: str) -> None:
    dead = dead_pid()
    orphan = start(image_id, dead, "true")
    owned = start(image_id, os.getpid(), "true")
    running = start(image_id, dead, "sleep", "60")
    try:
        for name in (orphan, owned):
            wait_until_exited(name)
        container.remove_orphans()
        assert (status(orphan), status(owned), status(running)) == (None, "exited", "running")
    finally:
        container.docker("rm", "--force", orphan, owned, running)


def test_owner_labels_that_are_not_a_pid_keep_the_container_and_spare_the_rest(
    image_id: str,
) -> None:
    dead = dead_pid()
    malformed = (
        "1\t2", f"{dead}\t2", f"{dead}\n2", f"{dead}\u0085x", "", "abc", "\u00b2", "0",
        "2147483648", "9" * 5000,
    )  # fmt: skip
    kept = [start(image_id, owner, "true") for owner in malformed]
    orphan = start(image_id, dead, "true")
    try:
        for name in (*kept, orphan):
            wait_until_exited(name)
        container.remove_orphans()
        assert [status(name) for name in kept] == ["exited"] * len(malformed)
        assert status(orphan) is None
    finally:
        container.docker("rm", "--force", *kept, orphan)


def test_a_non_ascii_owner_label_does_not_stop_server_start_under_an_ascii_locale(
    image_id: str,
) -> None:
    kept = start(image_id, "\u00b2", "true")
    ascii_locale = {**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
    try:
        wait_until_exited(kept)
        started = subprocess.run(
            (sys.executable, "-m", "cad.server"),
            env=ascii_locale,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        assert started.returncode == 0, started.stderr
        assert status(kept) == "exited"
    finally:
        container.docker("rm", "--force", kept)


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
        wait_until(lambda: not container.alive(server.pid))
        wait_until_exited(name)
        subprocess.run(cad_call("server_info", "{}"), env=env, check=True, capture_output=True)
        assert status(name) is None
    finally:
        client.kill()
        client.wait()
        if name is not None:
            container.docker("rm", "--force", name)
