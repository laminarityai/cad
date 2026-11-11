import subprocess
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from cad.verify.stamps import Stamps
from cad.verify.steps import ROOT, Step


@dataclass(frozen=True, slots=True)
class Ran:
    step: Step
    done: subprocess.CompletedProcess[str]
    seconds: float

    @property
    def passed(self) -> bool:
        return self.done.returncode == 0


@dataclass(frozen=True, slots=True)
class Skipped:
    """A fast step that passed before on exactly these inputs."""

    step: Step


def run_steps(steps: Sequence[Step], stamps: Stamps | None = None) -> int:
    """The fast steps share nothing, so they run side by side and every failure is shown. A slow
    step can need the one before it, as pytest needs the sandbox image, so those run in order
    and stop at the first failure. With stamps, a fast step whose inputs match its last pass is
    skipped; slow steps declare no inputs and always run."""
    fast = [step for step in steps if not step.slow]
    with ThreadPoolExecutor(max_workers=max(1, len(fast))) as pool:
        passed = all([_report(done) for done in pool.map(_run, fast, [stamps] * len(fast))])
    if not passed:
        return 1
    for step in steps:
        if step.slow and not _report(_run(step, stamps)):
            return 1
    return 0


def _run(step: Step, stamps: Stamps | None) -> Ran | Skipped:
    digest = stamps.digest(step) if stamps else None
    if stamps and digest and stamps.passed(step, digest):
        return Skipped(step)
    started = time.monotonic()
    done = subprocess.run(step.argv, capture_output=True, text=True, check=False, cwd=ROOT)
    ran = Ran(step, done, time.monotonic() - started)
    if stamps and digest:
        if ran.passed:
            stamps.record(step, digest)
        else:
            stamps.clear(step)
    return ran


def _report(done: Ran | Skipped) -> bool:
    if isinstance(done, Skipped):
        print(f"skip {done.step.name} (passed before on these inputs; --no-cache runs it)")
        return True
    if not done.passed:
        print(f"FAIL {done.step.name} ({done.seconds:.1f}s)")
        print(done.done.stdout, end="")
        print(done.done.stderr, end="")
        return False
    print(f"ok   {done.step.name} ({done.seconds:.1f}s)")
    if done.step.show_output:
        print(done.done.stdout, end="")
    return True
