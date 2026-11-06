import hashlib
import json
import os
import re
import secrets
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NewType, Self

from pydantic import model_validator

from cad.sandbox.outcome import Build, Built, SandboxUnavailable

VARIANTS_ROOT: Final = Path.home() / ".cad" / "variants"
CODE: Final = "code.py"
MANIFEST: Final = "build.json"
BREP: Final = "result.brep"
STEP: Final = "result.step"
ID_PATTERN: Final = re.compile(r"[0-9a-f]{16}")
MAX_FILE_BYTES: Final = 64 * 1024 * 1024
TRUSTED_DIRECTORIES: Final = (
    Path(__file__).resolve().parents[1] / "sandbox",
    Path(__file__).parent,
)

VariantId = NewType("VariantId", str)


class VariantRefused(Exception):
    pass


class UnknownVariant(VariantRefused):
    pass


class StaleVariant(VariantRefused):
    pass


class NotBuilt(VariantRefused):
    pass


def trust_digest(directories: tuple[Path, ...] = TRUSTED_DIRECTORIES) -> str:
    digest = hashlib.sha256()
    for directory in directories:
        for path in sorted(directory.glob("*.py")):
            digest.update(f"{directory.name}/{path.name}\0".encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


TRUST_DIGEST: Final = trust_digest()


def variant_id(code: str, image_tag: str) -> VariantId:
    key = json.dumps([image_tag, TRUST_DIGEST, code])
    return VariantId(hashlib.sha256(key.encode()).hexdigest()[:16])


def parse_variant_id(raw: str) -> VariantId:
    if ID_PATTERN.fullmatch(raw) is None:
        raise UnknownVariant(f"a variant id is 16 lowercase hex digits, not {raw!r}")
    return VariantId(raw)


def encode_code(code: str) -> bytes:
    return code.encode("utf-8", "surrogatepass")


class Manifest(Build):
    brep_sha256: str | None

    @model_validator(mode="after")
    def _hash_iff_built(self) -> Self:
        if isinstance(self.outcome, Built) != (self.brep_sha256 is not None):
            raise ValueError("brep_sha256 is set exactly when the outcome is built")
        return self


@dataclass(frozen=True, slots=True)
class Entry:
    id: VariantId
    directory: Path
    brep: bytes
    brep_sha256: str

    def attach_step(self, step: bytes) -> str:
        temporary = self.directory / f".step-{secrets.token_hex(8)}"
        try:
            temporary.write_bytes(step)
            os.replace(temporary, self.directory / STEP)
        finally:
            temporary.unlink(missing_ok=True)
        return hashlib.sha256(step).hexdigest()


def save(root: Path, vid: VariantId, code: str, build: Build, brep: bytes | None) -> Manifest:
    incoming = root / f".incoming-{secrets.token_hex(8)}"
    try:
        incoming.mkdir(parents=True)
        (incoming / CODE).write_bytes(encode_code(code))
        if brep is not None:
            (incoming / BREP).write_bytes(brep)
        manifest = Manifest(
            outcome=build.outcome,
            output=build.output,
            brep_sha256=None if brep is None else hashlib.sha256(brep).hexdigest(),
        )
        (incoming / MANIFEST).write_text(manifest.model_dump_json())
        try:
            incoming.rename(root / vid)
        except OSError:
            winner = read_manifest(root, vid)
            if winner is None:
                raise
            return winner
        return manifest
    finally:
        shutil.rmtree(incoming, ignore_errors=True)


def read_manifest(root: Path, vid: VariantId) -> Manifest | None:
    path = root / vid / MANIFEST
    try:
        return Manifest.model_validate_json(path.read_text())
    except FileNotFoundError:
        return None
    except ValueError as error:
        raise SandboxUnavailable(
            f"cannot read {path}; delete {path.parent} to build it again"
        ) from error


def open_entry(root: Path, raw_id: str, image_tag: str) -> Entry:
    vid = parse_variant_id(raw_id)
    directory = root / vid
    if not _is_directory(directory):
        raise UnknownVariant(f"no variant {vid} is stored; build its code with build_variant")
    if _stored_id(directory / CODE, image_tag) != vid:
        raise StaleVariant(
            f"variant {vid} was not stored by this version of the sandbox; build its code again"
        )
    manifest = _manifest(directory / MANIFEST, vid)
    if not isinstance(manifest.outcome, Built):
        raise NotBuilt(
            f"variant {vid} has no shape: its build ended as {manifest.outcome.kind}; "
            "fix the code and build it again"
        )
    brep = _read_regular(directory / BREP)
    brep_sha256 = hashlib.sha256(brep or b"").hexdigest()
    if brep is None or brep_sha256 != manifest.brep_sha256:
        raise StaleVariant(f"variant {vid} has a result.brep that its build did not store")
    return Entry(vid, directory, brep, brep_sha256)


def _stored_id(path: Path, image_tag: str) -> VariantId | None:
    code = _read_regular(path)
    if code is None:
        return None
    try:
        return variant_id(code.decode("utf-8", "surrogatepass"), image_tag)
    except UnicodeDecodeError:  # `encode_code` never writes such bytes, so the entry was edited
        return None


def _manifest(path: Path, vid: VariantId) -> Manifest:
    raw = _read_regular(path)
    try:
        return Manifest.model_validate_json(b"" if raw is None else raw)
    except ValueError as error:
        raise StaleVariant(
            f"variant {vid} has no build record this version of the sandbox can read; "
            "build its code again"
        ) from error


def _is_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _read_regular(path: Path) -> bytes | None:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            return None
        data = file.read(MAX_FILE_BYTES + 1)
    return None if len(data) > MAX_FILE_BYTES else data
