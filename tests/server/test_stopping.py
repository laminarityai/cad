import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from cad.checks import job_store
from tests.support.lanes import FEA, LONG, job

REPO = Path(__file__).parents[2]
SERVER = """
import sys
from pathlib import Path

from cad.checks import job_store
from cad.checks.lanes import Lanes
from cad.server.stopping import checks_end_with_the_server
from tests.support.lanes import FEA, GatedRunner, job, wait_until, with_fea

root = Path(sys.argv[1])
runner = GatedRunner()
runner.background.gate.clear()
lanes = Lanes(runner)
with checks_end_with_the_server(lanes):
    lanes.settle(with_fea(root), 0)
    wait_until(lambda: job_store.unfinished_runs(job(root, FEA)) == 1)
    print("running", flush=True)
    sys.stdin.read()
"""


@pytest.mark.parametrize(
    ("stop", "counted"), [(signal.SIGTERM, 0), (signal.SIGKILL, 1)], ids=["sigterm", "sigkill"]
)
def test_only_a_server_that_dies_mid_run_counts_the_run_as_interrupted(
    tmp_path: Path, stop: signal.Signals, counted: int
) -> None:
    server = subprocess.Popen(
        (sys.executable, "-c", SERVER, str(tmp_path)),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )
    try:
        assert server.stdout is not None
        assert server.stdout.readline() == b"running\n"
        assert job_store.unfinished_runs(job(tmp_path, FEA)) == 1
        server.send_signal(stop)
        assert server.wait(LONG) == -stop
        assert job_store.unfinished_runs(job(tmp_path, FEA)) == counted
    finally:
        server.kill()
        server.wait()
