import subprocess
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from cad.verify.steps import ROOT, Step


@dataclass(frozen=True, slots=True)
class Ran:
    step: Step
    done: subprocess.CompletedProcess[str]
    seconds: float

    @property
    def passed(self) -> bool:
        return self.done.returncode == 0


def run_steps(steps: Sequence[Step]) -> int:
    """The fast steps share nothing, so they run side by side and every failure is shown. A slow
    step can need the one before it, as pytest needs the sandbox image, so those run in order
    and stop at the first failure."""
    fast = [step for step in steps if not step.slow]
    with ThreadPoolExecutor(max_workers=max(1, len(fast))) as pool:
        passed = all([_report(ran) for ran in pool.map(_run, fast)])
    if not passed:
        return 1
    for step in steps:
        if step.slow and not _report(_run(step)):
            return 1
    return 0


def _run(step: Step) -> Ran:
    started = time.monotonic()
    done = subprocess.run(step.argv, capture_output=True, text=True, check=False, cwd=ROOT)
    return Ran(step, done, time.monotonic() - started)


def _report(ran: Ran) -> bool:
    if not ran.passed:
        print(f"FAIL {ran.step.name} ({ran.seconds:.1f}s)")
        print(ran.done.stdout, end="")
        print(ran.done.stderr, end="")
        return False
    print(f"ok   {ran.step.name} ({ran.seconds:.1f}s)")
    if ran.step.show_output:
        print(ran.done.stdout, end="")
    return True
