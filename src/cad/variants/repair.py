"""Heals the variant store without changing what a kept entry's checks read: a shape is written
back only as the bytes its signed record names, and a shape is deleted only where no reader opens
it."""

import hashlib
import logging
import os
from pathlib import Path
from typing import Final

from cad.errors import Unavailable
from cad.records import files
from cad.sandbox import builder, container, image
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants import entry

SHAPE_FILES: Final = (entry.BREP, entry.STEP)
ANOTHER_SHAPE: Final = (
    "variant {vid}'s stored shape was damaged, and its code did not build the same shape again; "
    "change its code, even by a comment, and build it as a new variant"
)
LOG = logging.getLogger(__name__)


class ShapeNotRebuilt(entry.StaleVariant):
    def __init__(self, vid: entry.VariantId) -> None:
        super().__init__(ANOTHER_SHAPE.format(vid=vid))


def heal(root: Path, raw_id: str, image_tag: str) -> None:
    """Rebuild a lost or altered result.brep of a current entry from the code its key signed, and
    keep the build only when it is the shape that signed record names, so every stored check result
    still reads the same bytes. Any other entry is left for `open_entry` to open or refuse."""
    refused = _refusal(root, raw_id, image_tag)
    if not isinstance(refused, entry.StaleVariant) or isinstance(refused, entry.OutdatedVariant):
        return
    vid = entry.parse_variant_id(raw_id)
    signed = _signed_code(root, vid, image_tag)
    if signed is None:
        return
    code, brep_sha256 = signed
    run = builder.build(code, image.current_image(image_tag), wall_seconds=container.WALL_SECONDS)
    brep = run.verdict.brep if isinstance(run.verdict, builder.Artifacts) else None
    if brep is None or hashlib.sha256(brep).hexdigest() != brep_sha256:
        LOG.error("%s: its signed code did not build the shape its record signed", root / vid)
        raise ShapeNotRebuilt(vid)
    files.replace(root / vid / entry.BREP, brep)


def collect_outdated(root: Path, vid: entry.VariantId, image_tag: str) -> bool:
    """Delete the shape files of an entry an earlier sandbox stored, once this sandbox stored a
    whole build of the same signed code. `open_entry` refuses an outdated id before it reads a
    shape, so no reader loses anything, and the entry keeps its code, signed record and check
    results to answer as outdated, with its code, as before."""
    if not any(os.path.lexists(root / vid / name) for name in SHAPE_FILES):
        return False
    outdated = _refusal(root, vid, image_tag)
    if not isinstance(outdated, entry.OutdatedVariant):
        return False
    if _refusal(root, entry.variant_id(outdated.code, image_tag), image_tag) is not None:
        return False
    for name in SHAPE_FILES:
        (root / vid / name).unlink(missing_ok=True)
    return True


def collect_beside(root: Path, vid: str, image_tag: str) -> None:
    """Collect every outdated build of the code `vid` holds. It runs after a score, so a fault is
    logged and never answered."""
    try:
        code = files.read_regular(
            root / entry.parse_variant_id(vid) / entry.CODE, entry.MAX_FILE_BYTES
        )
        text = None if code is None else code.decode("utf-8", "surrogatepass")
        for other in () if text is None else entry.built_from(root, text):
            if other != vid and collect_outdated(root, other, image_tag):
                LOG.info("collected the shapes of %s, outdated by %s", root / other, vid)
    except (OSError, ValueError, Unavailable, entry.VariantRefused) as error:
        LOG.error("cannot collect the outdated builds beside %s: %s", root / vid, error)


def _refusal(root: Path, raw_id: str, image_tag: str) -> entry.VariantRefused | None:
    try:
        entry.open_entry(root, raw_id, image_tag)
    except entry.VariantRefused as refused:
        return refused
    return None


def _signed_code(root: Path, vid: entry.VariantId, image_tag: str) -> tuple[str, str] | None:
    """The code and shape hash the key signed for `vid`, when that code still builds as `vid`."""
    code = files.read_regular(root / vid / entry.CODE, entry.MAX_FILE_BYTES)
    try:
        manifest = entry.read_manifest(root, vid)
    except SandboxUnavailable:
        return None
    if code is None or manifest is None or manifest.brep_sha256 is None:
        return None
    if manifest.code_sha256 != hashlib.sha256(code).hexdigest():
        return None
    text = code.decode("utf-8", "surrogatepass")
    return (text, manifest.brep_sha256) if entry.variant_id(text, image_tag) == vid else None
