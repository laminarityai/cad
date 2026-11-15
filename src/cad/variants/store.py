import hashlib
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from cad.sandbox import builder, container, image
from cad.sandbox.builder import Supplied
from cad.sandbox.outcome import Build, Built, PartUse, SandboxUnavailable, TimedOut
from cad.variants import entry

CAP_BYTES: Final = 2 * 2**30

type Fetch = Callable[[PartUse], bytes | None]
"""The stored BREP a part use names, read by its SHA-256 from the project it names, or None."""


class BuildResult(Build):
    variant_id: entry.VariantId


class RebuildFailed(entry.VariantRefused):
    def __init__(self, old: entry.VariantId, why: str) -> None:
        super().__init__(
            f"variant {old} was stored by an earlier version of the sandbox, and {why}"
        )


def no_parts(use: PartUse) -> None:
    """A fetch for a store whose builds read no part."""
    del use


def build_variant(
    code: str,
    root: Path = entry.VARIANTS_ROOT,
    *,
    parts: Sequence[Supplied] = (),
    wall_seconds: int = container.WALL_SECONDS,
    cap_bytes: int = CAP_BYTES,
) -> BuildResult:
    uses = tuple(one.use for one in parts)
    return _stored_or_built(code, uses, lambda: parts, root, wall_seconds, cap_bytes)


def rebuild(
    outdated: entry.OutdatedVariant, root: Path, fetch: Fetch, cap_bytes: int = CAP_BYTES
) -> BuildResult:
    """Build an outdated entry's signed code under this sandbox. Each part it read is fetched by
    the SHA-256 it was built with, so a part updated since rebuilds it with the old geometry."""

    def parts() -> tuple[Supplied, ...]:
        found = fetched(outdated.parts, fetch)
        if found is None:
            named = ", ".join(use.part_id for use in outdated.parts)
            raise RebuildFailed(
                outdated.id,
                f"the parts it read ({named}) no longer all have the geometry it was built "
                "with in their project",
            )
        return found

    code, uses = outdated.code, outdated.parts
    rebuilt = _stored_or_built(code, uses, parts, root, container.WALL_SECONDS, cap_bytes)
    if not isinstance(rebuilt.outcome, Built):
        raise RebuildFailed(
            outdated.id,
            f"its stored code did not build again as variant {rebuilt.variant_id}: "
            f"{rebuilt.model_dump_json()}",
        )
    return rebuilt


def fetched(uses: tuple[PartUse, ...], fetch: Fetch) -> tuple[Supplied, ...] | None:
    """Each part's BREP with the SHA-256 the build read it with, or None when one is gone."""
    found = [(use, fetch(use)) for use in uses]
    supplied = tuple(
        Supplied(use, brep)
        for use, brep in found
        if brep is not None and hashlib.sha256(brep).hexdigest() == use.brep_sha256
    )
    return supplied if len(supplied) == len(uses) else None


def _stored_or_built(
    code: str,
    uses: tuple[PartUse, ...],
    parts: Callable[[], Sequence[Supplied]],
    root: Path,
    wall_seconds: int,
    cap_bytes: int,
) -> BuildResult:
    """The stored build of the code and parts, or a new one. The parts' bytes are read only for
    a new build."""
    tag = image.image_tag(image.BUILD)
    vid = entry.variant_id(code, tag, uses)
    try:
        stored = entry.read_manifest(root, vid)
        if stored is None:
            refuse_if_full(root, cap_bytes)
            current = image.current_image(tag)
            stored = _build_and_store(code, vid, current, root, wall_seconds, parts())
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot use the variant store for variant {vid}", error, root
        ) from error
    return BuildResult(variant_id=vid, outcome=stored.outcome, output=stored.output)


def _build_and_store(
    code: str,
    vid: entry.VariantId,
    image_id: str,
    root: Path,
    wall_seconds: int,
    parts: Sequence[Supplied],
) -> Build:
    run = builder.build(code, image_id, wall_seconds=wall_seconds, parts=parts)
    if isinstance(run.verdict, builder.Artifacts):
        build, brep = Build(outcome=run.verdict.built, output=run.output), run.verdict.brep
    else:
        build, brep = Build(outcome=run.verdict, output=run.output), None
    if isinstance(build.outcome, TimedOut):
        return build
    return entry.save(root, vid, code, build, brep, tuple(one.use for one in parts))


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
