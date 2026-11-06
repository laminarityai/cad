from pathlib import Path

from cad.sandbox import container, host
from cad.sandbox.image import context_tar, current_image, image_tag
from cad.sandbox.outcome import Build, Built, SandboxUnavailable, TimedOut
from cad.variants import entry


class BuildResult(Build):
    variant_id: entry.VariantId


def build_variant(
    code: str, root: Path = entry.VARIANTS_ROOT, *, wall_seconds: int = container.WALL_SECONDS
) -> BuildResult:
    tag = image_tag(context_tar())
    vid = entry.variant_id(code, tag)
    try:
        stored = entry.read_manifest(root, vid)
        if stored is None:
            stored = build_and_store(code, vid, current_image(tag), root, wall_seconds)
    except OSError as error:
        raise SandboxUnavailable(f"cannot use the variant store at {root}: {error}") from error
    return BuildResult(variant_id=vid, outcome=stored.outcome, output=stored.output)


def build_and_store(
    code: str, vid: entry.VariantId, image_id: str, root: Path, wall_seconds: int
) -> Build:
    run = host.build(code, image_id, wall_seconds=wall_seconds)
    if isinstance(run.verdict, host.Artifacts):
        build, brep = Build(outcome=Built(), output=run.output), run.verdict.brep
    else:
        build, brep = Build(outcome=run.verdict, output=run.output), None
    if isinstance(build.outcome, TimedOut):
        return build
    return entry.save(root, vid, code, build, brep)
