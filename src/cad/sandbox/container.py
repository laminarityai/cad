import os
import re
import secrets
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from cad.sandbox import meter
from cad.sandbox.meter import Kind
from cad.sandbox.outcome import SandboxUnavailable

WALL_SECONDS = 60
ORPHAN_KILL_AFTER_DEADLINE_SECONDS = 5
MEMORY_MB = 2048
DOCKER_MEMORY_BUDGET_MB = 4096
PIDS = 128
CPUS = 2
TMPFS_MB = 256
REPORT_CAP = 64 * 1024 * 1024
OUTPUT_TAIL = 8 * 1024
CHUNK = 64 * 1024
DOCKER_TIMEOUT_SECONDS = 15
KILL_GRACE_SECONDS = 10
NO_DOCKER = "docker is not installed: no `docker` command on PATH"
STOPPING = "the server is stopping, so it ended this run and kept nothing from it; run it again"
OWNER = "cad.owner-pid"
PID = re.compile("[1-9][0-9]{0,9}")
PID_MAX = 2**31 - 1
ROW = TypeAdapter(tuple[str, str])

SLOTS = threading.Semaphore(DOCKER_MEMORY_BUDGET_MB // MEMORY_MB)
stopping = threading.Event()


@dataclass(frozen=True, slots=True)
class ReadOnlyMount:
    source: Path
    target: str


@dataclass(frozen=True, slots=True)
class Job:
    kind: Kind
    image_id: str
    command: tuple[str, ...]
    stdin: bytes
    mounts: tuple[ReadOnlyMount, ...] = ()
    wall_seconds: int = WALL_SECONDS
    memory_mb: int = MEMORY_MB
    tmpfs_mb: int = TMPFS_MB


@dataclass(frozen=True, slots=True)
class TooMuchOutput:
    pass


@dataclass(frozen=True, slots=True)
class Attended:
    killed_at_deadline: bool
    report: bytes | TooMuchOutput
    output: str


class ContainerState(BaseModel):
    model_config = ConfigDict(frozen=True)

    Status: str
    ExitCode: int
    OOMKilled: bool
    Error: str


@dataclass(frozen=True, slots=True)
class Ran:
    attended: Attended
    state: ContainerState


def label(kind: Kind) -> str:
    return f"cad.sandbox={kind}"


def remove_orphans() -> None:
    """Remove every sandbox container whose server is gone, running or not."""
    listed = docker(
        "ps", "--all", "--filter", "label=cad.sandbox",
        "--format", f'[{{{{json .Names}}}},{{{{json (.Label "{OWNER}")}}}}]',
    )  # fmt: skip
    if listed.returncode != 0:
        return
    owned = (owned_by(line) for line in listed.stdout.split("\n"))
    orphans = [name for name, pid in filter(None, owned) if not alive(pid)]
    if orphans:
        docker("rm", "--force", *orphans)


def stop_owned() -> None:
    """For a server that is stopping: refuse every later run and remove the containers this
    process started. A run whose container this removes raises instead of returning, so the
    server never keeps a result from a run it ended itself."""
    stopping.set()
    listed = docker("ps", "--all", "--quiet", "--filter", f"label={OWNER}={os.getpid()}")
    names = listed.stdout.split()
    if listed.returncode == 0 and names:
        docker("rm", "--force", *names)


def owned_by(row: str) -> tuple[str, int] | None:
    try:
        name, owner = ROW.validate_json(row)
    except ValidationError:
        return None
    if PID.fullmatch(owner) and int(owner) <= PID_MAX:
        return name, int(owner)
    return None


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run(job: Job) -> Ran:
    """Raises `SandboxUnavailable` when Docker is missing, down, or could not start the
    container, and its subclass `AccountLimitReached`, before anything starts, when the bound
    meter has nothing left."""
    name = f"cad-{job.kind}-{secrets.token_hex(8)}"
    with SLOTS, meter.charged(job.kind, ceiling_seconds(job)):
        _refuse_when_stopping()
        try:
            seen = attend(name, run_argv(name, job), job.stdin, job.wall_seconds)
            _refuse_when_stopping()
            state = inspect(name)
            if state is None or state.Status in {"created", "running"} or state.Error:
                cause = state.Error if state is not None and state.Error else seen.output
                raise SandboxUnavailable.hiding_host("docker could not run the sandbox", cause)
            return Ran(seen, state)
        finally:
            docker("rm", "--force", name)


def _refuse_when_stopping() -> None:
    if stopping.is_set():
        raise SandboxUnavailable(STOPPING)


def ceiling_seconds(job: Job) -> float:
    """The longest a container can be charged for: its limit, the in-container kill timer, and
    the grace `attend` gives `docker kill`."""
    return job.wall_seconds + ORPHAN_KILL_AFTER_DEADLINE_SECONDS + KILL_GRACE_SECONDS


def run_argv(name: str, job: Job) -> tuple[str, ...]:
    mounts = tuple(
        part
        for mount in job.mounts
        for part in ("--mount", f"type=bind,source={mount.source},target={mount.target},readonly")
    )
    return (
        "docker", "run", "--name", name, "--label", label(job.kind),
        "--label", f"{OWNER}={os.getpid()}",
        "--interactive", "--sig-proxy=false", "--init", "--pull", "never",
        "--log-driver", "none", "--network", "none",
        "--memory", f"{job.memory_mb}m", "--memory-swap", f"{job.memory_mb}m",
        "--pids-limit", str(PIDS), "--cpus", str(CPUS),
        "--read-only", "--tmpfs", f"/tmp:rw,noexec,nosuid,size={job.tmpfs_mb}m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534", "--env", "HOME=/tmp", "--workdir", "/tmp",
        *mounts,
        job.image_id,
        "timeout", "--signal", "KILL", str(job.wall_seconds + ORPHAN_KILL_AFTER_DEADLINE_SECONDS),
        *job.command,
    )  # fmt: skip


def attend(name: str, argv: tuple[str, ...], stdin: bytes, wall_seconds: int) -> Attended:
    """`killed_at_deadline` is true only when `docker kill` succeeded, so a container that exited on
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


def read_head(stream: IO[bytes], cap: int) -> bytes | TooMuchOutput:
    kept = bytearray()
    over = False
    while chunk := stream.read(CHUNK):
        over = over or len(kept) + len(chunk) > cap
        if not over:
            kept += chunk
    return TooMuchOutput() if over else bytes(kept)


def read_tail(stream: IO[bytes], cap: int) -> bytes:
    kept = b""
    while chunk := stream.read(CHUNK):
        kept = (kept + chunk)[-cap:]
    return kept


def inspect(name: str) -> ContainerState | None:
    done = docker("container", "inspect", "--format", "{{json .State}}", name)
    if done.returncode != 0:
        return None
    return ContainerState.model_validate_json(done.stdout)


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ("docker", *args),
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=DOCKER_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as error:
        raise SandboxUnavailable(NO_DOCKER) from error
    except subprocess.TimeoutExpired as error:
        raise SandboxUnavailable(
            f"docker did not answer `docker {args[0]}` within {DOCKER_TIMEOUT_SECONDS} s"
        ) from error
