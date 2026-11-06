import hashlib
import io
import subprocess
import tarfile
from pathlib import Path

from cad.sandbox.container import docker, first_line
from cad.sandbox.outcome import SandboxUnavailable

SANDBOX_DIR = Path(__file__).resolve().parents[3] / "sandbox"
CONTEXT = ("Dockerfile", "requirements.txt")
REPOSITORY = "cad-sandbox"
BUILD_IMAGE = "uv run cad-sandbox build-image"


def context_tar(directory: Path = SANDBOX_DIR) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in CONTEXT:
            data = (directory / name).read_bytes()
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mtime = 0
            entry.mode = 0o644
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = ""
            tar.addfile(entry, io.BytesIO(data))
    return buffer.getvalue()


def image_tag(context: bytes) -> str:
    return f"{REPOSITORY}:{hashlib.sha256(context).hexdigest()[:12]}"


def find_image(tag: str) -> str | None:
    done = docker("images", "--quiet", "--no-trunc", tag)
    if done.returncode != 0:
        raise SandboxUnavailable(f"docker is not reachable: {first_line(done.stderr)}")
    return next(iter(done.stdout.split()), None)


def current_image(tag: str) -> str:
    image_id = find_image(tag)
    if image_id is None:
        raise SandboxUnavailable(f"sandbox image {tag} is missing; run `{BUILD_IMAGE}`")
    return image_id


def build_image() -> str:
    context = context_tar()
    tag = image_tag(context)
    if find_image(tag) is not None:
        return f"sandbox image {tag} is current"
    done = subprocess.run(("docker", "build", "--tag", tag, "-"), input=context, check=False)
    if done.returncode != 0:
        raise SandboxUnavailable(f"docker build of {tag} failed with exit code {done.returncode}")
    return f"built sandbox image {tag}"
