"""The variant store: one directory per variant id, written once, read by id.

    <root>/<id>/code.py              the code as given, never run on the host
    <root>/<id>/build.json           a cad.sandbox.outcome.Build
    <root>/<id>/result.brep          only when the outcome is Built
    <root>/<id>/result.step          only when the outcome is Built
    <root>/.incoming-<random>/       a build in progress, which no reader looks at

A directory named by an id is complete or absent, because it appears by one rename of a finished
temporary directory.
"""

import hashlib
import json
import secrets
import shutil
from pathlib import Path
from typing import NewType

from cad.sandbox import host
from cad.sandbox.image import context_tar, current_image, image_tag
from cad.sandbox.outcome import Build, SandboxUnavailable, TimedOut

VARIANTS_ROOT = Path.home() / ".cad" / "variants"
ID_SCHEME = "cad-variant-1"
"""Bump when Build changes shape, so newer code never reads an older build.json."""
ID_HEX = 16

VariantId = NewType("VariantId", str)


class BuildResult(Build):
    variant_id: VariantId


def variant_id(code: str, tag: str) -> VariantId:
    """Needs no Docker, so a stored variant is returned while Docker is down."""
    runner = hashlib.sha256(host.RUNNER.encode()).hexdigest()
    key = json.dumps([ID_SCHEME, tag, runner, code])
    return VariantId(hashlib.sha256(key.encode()).hexdigest()[:ID_HEX])


def build_variant(
    code: str, root: Path = VARIANTS_ROOT, *, wall_seconds: int = host.WALL_SECONDS
) -> BuildResult:
    """Build `code`, or return the stored build when this code already built on this image.

    TimedOut is returned but not stored, because it depends on how busy the host was, so the same
    code gets a fresh attempt next time. Raises SandboxUnavailable only.
    """
    tag = image_tag(context_tar())
    vid = variant_id(code, tag)
    try:
        stored = load(root, vid)
        if stored is not None:
            return stored
        return build_and_store(code, vid, current_image(tag), root, wall_seconds)
    except OSError as error:
        raise SandboxUnavailable(f"cannot use the variant store at {root}: {error}") from error


def build_and_store(
    code: str, vid: VariantId, image_id: str, root: Path, wall_seconds: int
) -> BuildResult:
    incoming = root / f".incoming-{secrets.token_hex(8)}"
    try:
        incoming.mkdir(parents=True)
        (incoming / "code.py").write_bytes(host.encoded(code))
        build = host.build(code, image_id, incoming, wall_seconds=wall_seconds)
        result = BuildResult(variant_id=vid, outcome=build.outcome, output=build.output)
        if isinstance(build.outcome, TimedOut):
            return result
        (incoming / "build.json").write_text(build.model_dump_json())
        try:
            incoming.rename(root / vid)
        except OSError:
            winner = load(root, vid)
            if winner is None:
                raise
            return winner
        return result
    finally:
        shutil.rmtree(incoming, ignore_errors=True)


def load(root: Path, vid: VariantId) -> BuildResult | None:
    """Only this module writes build.json, so a file that does not parse is a bug, not a state."""
    try:
        stored = (root / vid / "build.json").read_text()
    except FileNotFoundError:
        return None
    build = Build.model_validate_json(stored)
    return BuildResult(variant_id=vid, outcome=build.outcome, output=build.output)
