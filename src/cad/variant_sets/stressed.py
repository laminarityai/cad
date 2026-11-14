"""Whether a brief has a stress result yet. The result rule for a described load case reads it."""

from pathlib import Path

from cad.checks import stored
from cad.checks.container import fea
from cad.records.roots import Roots
from cad.variant_sets.store import members, set_key
from cad.variants import entry


def has_stress_result(roots: Roots, variants: Path, brief_id: str) -> bool:
    """True when any variant stored with the code of a revision of the brief's set has a stored
    `fea` result, whatever its verdict and whichever sandbox built it. `built_as` also counts an
    entry stored before the code index existed. A variant of other code does not count."""
    built = {
        one
        for member in members(roots.projects, set_key(roots, brief_id))
        for revision in member.revisions
        for one in (revision.built_as, *entry.built_from(variants, revision.code))
    }
    return any(stored.has_result(variants, variant, fea.ID) for variant in sorted(built))
