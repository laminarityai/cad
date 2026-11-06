"""Run one variant build in a fresh, locked-down container and decide its BuildOutcome.

Trusted: whether the host's own `docker kill` ended the run, and the exit code, OOM flag and run
state that `docker inspect` reports. Untrusted: every byte the container writes. The host keeps
at most REPORT_CAP bytes of it, validates them as one `wire.Report`, caps every string, writes
every message the agent reads, and writes the result files itself.
"""

import binascii
import secrets
import subprocess
import threading
from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Annotated

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from cad.sandbox.outcome import (
    Build,
    BuildFailed,
    Built,
    Failure,
    NoResult,
    OutOfMemory,
    SandboxUnavailable,
    TimedOut,
)
from cad.sandbox.wire import Report

WALL_SECONDS = 60
IN_CONTAINER_GRACE_SECONDS = 5
"""The in-container `timeout` fires this long after the host's deadline, so a build whose host
died still stops."""
MEMORY_MB = 2048
PIDS = 128
CPUS = 2
TMPFS_MB = 256
REPORT_CAP = 64 * 1024 * 1024
OUTPUT_TAIL = 8 * 1024
TEXT_CAP = 8 * 1024
CHUNK = 64 * 1024
DOCKER_TIMEOUT_SECONDS = 15
KILL_GRACE_SECONDS = 10
SIGXCPU_EXIT = 128 + 24
CONTRACT = "assign the final shape to `result`"
LABEL = "cad.sandbox=build"
NO_DOCKER = "docker is not installed: no `docker` command on PATH"
RUNNER = Path(__file__).with_name("runner.py").read_text()

REPORT = TypeAdapter[Report](Annotated[Report, Field(discriminator="kind")])
SLOTS = threading.Semaphore(2)
"""Two 2 GB builds at once fill most of an 8 GB Docker VM."""


@dataclass(frozen=True, slots=True)
class Artifacts:
    brep: bytes
    step: bytes


@dataclass(frozen=True, slots=True)
class Attended:
    """What the host saw while the docker CLI ran. `report` is None when stdout passed the cap."""

    killed_at_deadline: bool
    report: bytes | None
    output: str


class ContainerState(BaseModel):
    """The fields of `docker inspect`'s State that decide an outcome."""

    model_config = ConfigDict(frozen=True)

    Status: str
    ExitCode: int
    OOMKilled: bool
    Error: str


def encoded(code: str) -> bytes:
    """The bytes the container runs. A lone surrogate survives, so the runner fails on it."""
    return code.encode("utf-8", "surrogatepass")


def build(code: str, image_id: str, into: Path, *, wall_seconds: int = WALL_SECONDS) -> Build:
    """Build `code` in a new container. Writes result.brep and result.step into `into` only when
    the outcome is Built. Raises SandboxUnavailable only when Docker itself failed."""
    name = f"cad-build-{secrets.token_hex(8)}"
    with SLOTS:
        try:
            seen = attend(name, run_argv(name, image_id, wall_seconds), encoded(code), wall_seconds)
            state = inspect(name)
            if state is None or state.Status == "created" or state.Error:
                cause = state.Error if state is not None and state.Error else seen.output
                raise SandboxUnavailable(f"docker could not run the sandbox: {first_line(cause)}")
            verdict = classify(seen, state, wall_seconds)
        finally:
            docker("rm", "--force", name)
    if isinstance(verdict, Artifacts):
        (into / "result.brep").write_bytes(verdict.brep)
        (into / "result.step").write_bytes(verdict.step)
        return Build(outcome=Built(), output=seen.output)
    return Build(outcome=verdict, output=seen.output)


def run_argv(name: str, image_id: str, wall_seconds: int) -> tuple[str, ...]:
    """No --rm, so the host can inspect the container before it removes it. The image id, not
    the tag, so a rebuild between lookup and run cannot change which image runs."""
    return (
        "docker", "run", "--name", name, "--label", LABEL,
        "--interactive", "--init", "--pull", "never", "--log-driver", "none",
        "--network", "none",
        "--memory", f"{MEMORY_MB}m", "--memory-swap", f"{MEMORY_MB}m",
        "--pids-limit", str(PIDS), "--cpus", str(CPUS),
        "--read-only", "--tmpfs", f"/tmp:rw,noexec,nosuid,size={TMPFS_MB}m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534", "--env", "HOME=/tmp", "--workdir", "/tmp",
        image_id,
        "timeout", "--signal", "KILL", str(wall_seconds + IN_CONTAINER_GRACE_SECONDS),
        "python", "-I", "-c", RUNNER, str(wall_seconds),
    )  # fmt: skip


def attend(name: str, argv: tuple[str, ...], stdin: bytes, wall_seconds: int) -> Attended:
    """Run the docker CLI, feed stdin, drain both outputs within their caps, and own the deadline.

    `killed_at_deadline` is true only when `docker kill` succeeded, so a container that exited on
    its own just before the deadline keeps its report.
    """
    try:
        process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except FileNotFoundError as error:
        raise SandboxUnavailable(NO_DOCKER) from error
    with process, ThreadPoolExecutor(max_workers=3) as pool:
        pool.submit(feed, pipe(process.stdin), stdin)
        head = pool.submit(read_head, pipe(process.stdout), REPORT_CAP)
        tail = pool.submit(read_tail, pipe(process.stderr), OUTPUT_TAIL)
        killed = False
        try:
            process.wait(timeout=wall_seconds)
        except subprocess.TimeoutExpired:
            killed = docker("kill", name).returncode == 0
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=KILL_GRACE_SECONDS)
        finally:
            process.kill()
        return Attended(
            killed_at_deadline=killed,
            report=head.result(),
            output=tail.result().decode("utf-8", errors="replace"),
        )


def pipe[T](stream: T | None) -> T:
    assert stream is not None, "Popen was given PIPE for every stream"
    return stream


def feed(stream: IO[bytes], data: bytes) -> None:
    with suppress(BrokenPipeError), stream:
        stream.write(data)


def read_head(stream: IO[bytes], cap: int) -> bytes | None:
    """The stream's bytes, read to EOF, or None when there were more than `cap`."""
    kept = bytearray()
    over = False
    while chunk := stream.read(CHUNK):
        over = over or len(kept) + len(chunk) > cap
        if not over:
            kept += chunk
    return None if over else bytes(kept)


def read_tail(stream: IO[bytes], cap: int) -> bytes:
    kept = b""
    while chunk := stream.read(CHUNK):
        kept = (kept + chunk)[-cap:]
    return kept


def inspect(name: str) -> ContainerState | None:
    """The container's State, or None when Docker cannot show it."""
    done = docker("container", "inspect", "--format", "{{json .State}}", name)
    if done.returncode != 0:
        return None
    return ContainerState.model_validate_json(done.stdout)


def classify(seen: Attended, state: ContainerState, wall_seconds: int) -> Artifacts | Failure:
    """Trusted facts first, then the report, then the exit code.

    A valid report beats an OOM kill, because the shape was still produced. Exit code 137 alone
    never means TimedOut: the variant can SIGKILL the in-container `timeout` itself.
    """
    if seen.killed_at_deadline:
        return TimedOut(limit_seconds=wall_seconds)
    claimed = reported(seen.report) if state.ExitCode == 0 and seen.report else None
    if claimed is not None:
        return claimed
    if state.OOMKilled:
        return OutOfMemory(limit_mb=MEMORY_MB)
    if state.ExitCode == SIGXCPU_EXIT:
        return TimedOut(limit_seconds=wall_seconds)
    if seen.report is None:
        return died(f"the build sent more than {REPORT_CAP // 2**20} MiB of output")
    if state.ExitCode == 0 and seen.report:
        return died("the build sent a malformed result")
    return died(f"the build process exited with code {state.ExitCode} before it sent a result")


def died(error: str) -> BuildFailed:
    return BuildFailed(error=error, traceback="")


def reported(raw: bytes) -> Artifacts | Failure | None:
    """The outcome one valid report claims, or None for anything else."""
    try:
        report = REPORT.validate_json(raw, strict=True)
    except ValidationError:
        return None
    if report["kind"] == "built":
        try:
            brep = b64decode(report["brep"], validate=True)
            step = b64decode(report["step"], validate=True)
        except binascii.Error:
            return None
        return Artifacts(brep, step)
    if report["kind"] == "build_failed":
        return BuildFailed(
            error=report["error"][:TEXT_CAP], traceback=report["traceback"][-TEXT_CAP:]
        )
    if report["found"] is None:
        return NoResult(reason=f"the code never assigned `result`; {CONTRACT}")
    found = report["found"][:TEXT_CAP]
    return NoResult(reason=f"`result` is of type {found}, not a build123d Shape; {CONTRACT}")


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    """A short docker command. A missing binary or a hung daemon is SandboxUnavailable."""
    try:
        return subprocess.run(
            ("docker", *args),
            capture_output=True,
            text=True,
            check=False,
            timeout=DOCKER_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as error:
        raise SandboxUnavailable(NO_DOCKER) from error
    except subprocess.TimeoutExpired as error:
        raise SandboxUnavailable(
            f"docker did not answer `docker {args[0]}` within {DOCKER_TIMEOUT_SECONDS} s"
        ) from error


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "no message")
