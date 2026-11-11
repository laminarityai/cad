"""Bind a stored scorecard to the signed build record of its variant.

`build.json` is signed by the store, and `entry.read_manifest` is the verified way to read it. The
card is bound when it names the shape that build stored and, when it says a STEP is stored, the
STEP file on disk has the hash it names.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from cad.checks.result import StepStored
from cad.records import key
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard.model import Scorecard
from cad.variants import entry


@dataclass(frozen=True, slots=True)
class Unbound:
    reason: str


def bind(root: Path, card: Scorecard) -> Unbound | None:
    try:
        vid = entry.parse_variant_id(card.variant_id)
    except entry.VariantRefused as error:
        return Unbound(str(error))
    if not key.key_path(root).is_file():
        return Unbound(f"the store has no key at {key.key_path(root)}, so no build is signed")
    try:
        manifest = entry.read_manifest(root, vid)
    except SandboxUnavailable:
        return Unbound(
            f"variant {vid} has a build record that this store did not sign or that cannot be read"
        )
    if manifest is None:
        return Unbound(f"variant {vid} has no build record")
    if manifest.brep_sha256 is None:
        return Unbound(f"variant {vid} was built without a shape ({manifest.outcome.kind})")
    if manifest.brep_sha256 != card.brep_sha256:
        return Unbound(
            f"the card measured shape {card.brep_sha256[:12]}, "
            f"but the signed build stored {manifest.brep_sha256[:12]}"
        )
    if isinstance(card.step, StepStored):
        return _step_unbound(root / vid / entry.STEP, card.step.sha256)
    return None


@dataclass(frozen=True, slots=True)
class Unlinked:
    reason: str


def link(root: Path, card: Scorecard) -> Unlinked | None:
    """A card with `rebuilt_from` is linked when the old entry's signed record pins the same code
    as the signed record of the variant the card scored."""
    if card.rebuilt_from is None:
        return None
    try:
        old = entry.parse_variant_id(card.rebuilt_from)
        new = entry.parse_variant_id(card.variant_id)
    except entry.VariantRefused as error:
        return Unlinked(str(error))
    if not key.key_path(root).is_file():
        return Unlinked(f"the store has no key at {key.key_path(root)}, so no build is signed")
    try:
        old_manifest = entry.read_manifest(root, old)
        new_manifest = entry.read_manifest(root, new)
    except SandboxUnavailable:
        return Unlinked(
            f"variant {old} or {new} has a build record that this store did not sign "
            "or that cannot be read"
        )
    if old_manifest is None or old_manifest.code_sha256 is None:
        return Unlinked(f"the card says it was rebuilt from {old}, which pins no code")
    if new_manifest is None or new_manifest.code_sha256 != old_manifest.code_sha256:
        return Unlinked(f"variant {new} was not built from the code that {old} stored")
    return None


def _step_unbound(path: Path, sha256: str) -> Unbound | None:
    try:
        held = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return Unbound(f"the card says a STEP is stored, but {path.name} cannot be read")
    if held != sha256:
        return Unbound(f"the card names STEP {sha256[:12]}, but {path.name} is {held[:12]}")
    return None
