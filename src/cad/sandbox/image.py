import hashlib
import io
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cad.sandbox.container import docker
from cad.sandbox.outcome import SandboxUnavailable

SANDBOX_DIR: Final = Path(__file__).resolve().parents[3] / "sandbox"
BUILD_IMAGE: Final = "uv run cad-sandbox build-image"


@dataclass(frozen=True, slots=True)
class Image:
    repository: str
    directory: Path
    context: tuple[str, ...]
    base: "Image | None" = None


BUILD: Final = Image("cad-sandbox", SANDBOX_DIR, ("Dockerfile", "requirements.txt"))
ANALYSIS: Final = Image("cad-analysis", SANDBOX_DIR / "analysis", ("Dockerfile",), base=BUILD)
IMAGES: Final = (BUILD, ANALYSIS)


def context_tar(image: Image) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in image.context:
            data = (image.directory / name).read_bytes()
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mtime = 0
            entry.mode = 0o644
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = ""
            tar.addfile(entry, io.BytesIO(data))
    return buffer.getvalue()


def image_tag(image: Image) -> str:
    digest = hashlib.sha256(context_tar(image))
    if image.base is not None:
        digest.update(image_tag(image.base).encode())
    return f"{image.repository}:{digest.hexdigest()[:12]}"


def find_image(tag: str) -> str | None:
    done = docker("images", "--quiet", "--no-trunc", tag)
    if done.returncode != 0:
        raise SandboxUnavailable.hiding_host("docker is not reachable", done.stderr)
    return next(iter(done.stdout.split()), None)


def current_image(tag: str) -> str:
    image_id = find_image(tag)
    if image_id is None:
        raise SandboxUnavailable(f"sandbox image {tag} is missing; run `{BUILD_IMAGE}`")
    return image_id


def build_images() -> str:
    return "\n".join(build_image(image) for image in IMAGES)


def build_image(image: Image) -> str:
    tag = image_tag(image)
    if find_image(tag) is not None:
        return f"sandbox image {tag} is current"
    base = () if image.base is None else ("--build-arg", f"BASE={image_tag(image.base)}")
    done = subprocess.run(
        ("docker", "build", "--tag", tag, *base, "-"), input=context_tar(image), check=False
    )
    if done.returncode != 0:
        raise SandboxUnavailable(f"docker build of {tag} failed with exit code {done.returncode}")
    return f"built sandbox image {tag}"
