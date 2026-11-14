import os
from pathlib import Path
from typing import Final

from cad.sandbox import container, host, image
from cad.sandbox.outcome import Build, SandboxUnavailable, TimedOut
from cad.variants import entry

CAP_BYTES: Final = 2 * 2**30


class BuildResult(Build):
    variant_id: entry.VariantId


class RebuildFailed(entry.VariantRefused):
    def __init__(self, old: entry.VariantId, rebuilt: BuildResult) -> None:
        super().__init__(
            f"variant {old} was stored by an earlier version of the sandbox, and its stored code "
            f"did not build again as variant {rebuilt.variant_id}: {rebuilt.model_dump_json()}"
        )


def build_variant(
    code: str,
    root: Path = entry.VARIANTS_ROOT,
    *,
    wall_seconds: int = container.WALL_SECONDS,
    cap_bytes: int = CAP_BYTES,
) -> BuildResult:
    tag = image.image_tag(image.BUILD)
    vid = entry.variant_id(code, tag)
    try:
        stored = entry.read_manifest(root, vid)
        if stored is None:
            refuse_if_full(root, cap_bytes)
            stored = build_and_store(code, vid, image.current_image(tag), root, wall_seconds)
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
        build, brep = Build(outcome=run.verdict.built, output=run.output), run.verdict.brep
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
            f"this account's variant store is full ({used} of {cap_bytes} bytes), so no code can "
            "be built until space is freed, including the rebuild an older variant needs before "
            "it is scored; a variant built by this version of the server can still be "
            "scored"
        )


def _size_if_present(path: Path) -> int:
    try:
        return path.lstat().st_size
    except FileNotFoundError:
        return 0
