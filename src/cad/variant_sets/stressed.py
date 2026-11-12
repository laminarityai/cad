"""Whether a brief has a stress result yet. The result rule for a described load case reads it."""

from pathlib import Path

from cad.checks import stored
from cad.checks.container import fea
from cad.records.roots import Roots
from cad.variant_sets.store import members, set_key


def has_stress_result(roots: Roots, variants: Path, brief_id: str) -> bool:
    """True when any variant a slot of the brief's set has built has a stored `fea` result,
    whatever its verdict. A variant built outside the set does not count."""
    built = {
        revision.built_as
        for member in members(roots.projects, set_key(roots, brief_id))
        for revision in member.revisions
    }
    return any(stored.has_result(variants, variant, fea.ID) for variant in sorted(built))
