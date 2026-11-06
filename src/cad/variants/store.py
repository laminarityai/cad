import hashlib
import json
import secrets
import shutil
from pathlib import Path
from typing import NewType

from cad.sandbox import container, host
from cad.sandbox.image import context_tar, current_image, image_tag
from cad.sandbox.outcome import Build, Built, Failure, SandboxUnavailable, TimedOut

VARIANTS_ROOT = Path.home() / ".cad" / "variants"
CODE = "code.py"
BUILD = "build.json"
BREP = "result.brep"
STEP = "result.step"
ID_HEX = 16

VariantId = NewType("VariantId", str)


class BuildResult(Build):
    variant_id: VariantId


def variant_id(code: str, tag: str) -> VariantId:
    schema = json.dumps(Build.model_json_schema(), sort_keys=True)
    runner = hashlib.sha256(host.RUNNER.encode()).hexdigest()
    key = json.dumps([schema, tag, runner, code])
    return VariantId(hashlib.sha256(key.encode()).hexdigest()[:ID_HEX])


def build_variant(
    code: str, root: Path = VARIANTS_ROOT, *, wall_seconds: int = container.WALL_SECONDS
) -> BuildResult:
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
        (incoming / CODE).write_bytes(host.utf8_keeping_surrogates(code))
        run = host.build(code, image_id, wall_seconds=wall_seconds)
        outcome: Built | Failure
        if isinstance(run.verdict, host.Artifacts):
            (incoming / BREP).write_bytes(run.verdict.brep)
            (incoming / STEP).write_bytes(run.verdict.step)
            outcome = Built()
        else:
            outcome = run.verdict
        result = BuildResult(variant_id=vid, outcome=outcome, output=run.output)
        if isinstance(outcome, TimedOut):
            return result
        (incoming / BUILD).write_text(Build(outcome=outcome, output=run.output).model_dump_json())
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
    path = root / vid / BUILD
    try:
        build = Build.model_validate_json(path.read_text())
    except FileNotFoundError:
        return None
    except ValueError as error:
        raise SandboxUnavailable(
            f"cannot read {path}; delete {path.parent} to build it again"
        ) from error
    return BuildResult(variant_id=vid, outcome=build.outcome, output=build.output)
