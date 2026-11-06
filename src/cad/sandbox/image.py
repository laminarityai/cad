"""The sandbox image: its content-addressed tag, finding it, and building it.

The tag is a digest of the exact build context, so editing the Dockerfile or the lock gives a new
tag and a stale image is never run. "Is the image current" is "does the tag exist".
"""

import hashlib
import io
import subprocess
import tarfile
from pathlib import Path

from cad.sandbox.host import docker, first_line
from cad.sandbox.outcome import SandboxUnavailable

SANDBOX_DIR = Path(__file__).resolve().parents[3] / "sandbox"
CONTEXT = ("Dockerfile", "requirements.txt")
REPOSITORY = "cad-sandbox"
BUILD_IMAGE = "uv run cad-sandbox build-image"


def context_tar(directory: Path = SANDBOX_DIR) -> bytes:
    """The whole build context as a tar with fixed metadata, so equal files give equal bytes."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in CONTEXT:
            data = (directory / name).read_bytes()
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            tar.addfile(entry, io.BytesIO(data))
    return buffer.getvalue()


def image_tag(context: bytes) -> str:
    return f"{REPOSITORY}:{hashlib.sha256(context).hexdigest()[:12]}"


def find_image(tag: str) -> str | None:
    """The image id for `tag`, or None when Docker has no such image."""
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
    """Build the image for the context on disk unless it exists. Returns a one-line status."""
    context = context_tar()
    tag = image_tag(context)
    if find_image(tag) is not None:
        return f"sandbox image {tag} is current"
    done = subprocess.run(("docker", "build", "--tag", tag, "-"), input=context, check=False)
    if done.returncode != 0:
        raise SandboxUnavailable(f"docker build of {tag} failed with exit code {done.returncode}")
    return f"built sandbox image {tag}"
