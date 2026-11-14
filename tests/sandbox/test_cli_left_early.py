import subprocess

import pytest

from cad.sandbox import container

JOB = container.Job(kind="check", image_id="sha256:none", command=("true",), stdin=b"")
RUNNING = '{"Status": "running", "ExitCode": 0, "OOMKilled": false, "Error": ""}'


def test_a_docker_cli_that_left_while_its_container_runs_is_refused_and_not_read_as_a_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def attend(*_: object) -> container.Attended:
        return container.Attended(killed_at_deadline=False, report=b'{"half', output="")

    def docker(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, RUNNING if "inspect" in args else "", "")

    monkeypatch.setattr(container, "attend", attend)
    monkeypatch.setattr(container, "docker", docker)
    with pytest.raises(container.SandboxUnavailable, match="docker could not run the sandbox"):
        container.run(JOB)
