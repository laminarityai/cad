import subprocess
import time
from collections.abc import Sequence

from cad.verify.steps import ROOT, Step


def run_steps(steps: Sequence[Step]) -> int:
    for step in steps:
        started = time.monotonic()
        done = subprocess.run(step.argv, capture_output=True, text=True, check=False, cwd=ROOT)
        seconds = time.monotonic() - started
        if done.returncode != 0:
            print(f"FAIL {step.name} ({seconds:.1f}s)")
            print(done.stdout, end="")
            print(done.stderr, end="")
            return 1
        print(f"ok   {step.name} ({seconds:.1f}s)")
        if step.show_output:
            print(done.stdout, end="")
    return 0
