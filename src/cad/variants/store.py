import os
from pathlib import Path
from typing import Final

from cad.sandbox import container, host
from cad.sandbox.image import context_tar, current_image, image_tag
from cad.sandbox.outcome import Build, Built, SandboxUnavailable, TimedOut
from cad.variants import entry

CAP_BYTES: Final = 2 * 2**30


class BuildResult(Build):
    variant_id: entry.VariantId


def build_variant(
    code: str,
    root: Path = entry.VARIANTS_ROOT,
    *,
    wall_seconds: int = container.WALL_SECONDS,
    cap_bytes: int = CAP_BYTES,
) -> BuildResult:
    tag = image_tag(context_tar())
    vid = entry.variant_id(code, tag)
    try:
        stored = entry.read_manifest(root, vid)
        if stored is None:
            refuse_if_full(root, cap_bytes)
            stored = build_and_store(code, vid, current_image(tag), root, wall_seconds)
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot use the variant store for variant {vid}", error, root
        ) from error
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


def refuse_if_full(root: Path, cap_bytes: int) -> None:
    used = sum(
        _size_if_present(Path(directory) / name)
        for directory, _, names in os.walk(root)
        for name in names
    )
    if used >= cap_bytes:
        raise SandboxUnavailable(
            f"the variant store holds {used} bytes, at its limit of {cap_bytes} bytes; "
            "the operator must delete variants before new code can be built"
        )


def _size_if_present(path: Path) -> int:
    try:
        return path.lstat().st_size
    except FileNotFoundError:
        return 0
