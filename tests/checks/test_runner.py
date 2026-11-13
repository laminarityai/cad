"""The check container's runner and report channel, run in a process of their own, with a kernel
whose STEP writer kills that process as the kernel's out-of-memory killer would."""

import json
import subprocess
import sys
from pathlib import Path

from cad.checks.report import QUICK, build_request, parse
from cad.checks.result import StepMissing, Verdict
from cad.sandbox.container import Attended, ContainerState, Job, Ran
from cad.tables.materials import load_materials
from tests.support.check_fakes import REPORT_CAP

ROOT = Path(__file__).parents[2]
LIMITS = Job("check", "sha256:analysis", (), b"", wall_seconds=60, memory_mb=1536)
DIES_WRITING_STEP = """import json, os, signal
from cad.checks.container.channel import serve
from cad.checks.container.runner import run
from tests.support.check_fakes import FakeKernel

class DiesWritingStep(FakeKernel):
    def step_bytes(self, shape, room):
        os.kill(os.getpid(), signal.SIGKILL)

serve(lambda args, brep: run(json.loads(args[0]), brep, DiesWritingStep(), int(args[1])))
"""


def test_the_verdicts_reach_the_host_when_the_container_dies_writing_the_step() -> None:
    request = build_request("prusament-pla", load_materials())
    died = subprocess.run(
        [sys.executable, "-c", DIES_WRITING_STEP, "60", json.dumps(request.wire), str(REPORT_CAP)],
        input=b"brep",
        capture_output=True,
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT)},
        check=False,
    )
    assert died.returncode == -9, died.stderr.decode()
    state = ContainerState(Status="exited", ExitCode=137, OOMKilled=True, Error="")
    seen = Attended(killed_at_deadline=False, report=died.stdout, output="")
    parsed = parse(Ran(seen, state), request, LIMITS)
    assert [(one.check_id, one.verdict) for one in parsed.results] == [
        (spec.id, Verdict.PASS) for spec in QUICK
    ]
    assert parsed.step == StepMissing(
        reason="the check container ran out of memory (1536 MB) while it wrote the STEP"
    )
