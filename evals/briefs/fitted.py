"""A fit result measures a variant against a context part. Its instance must name a part a
person confirmed in the card's project, whose stored BREP still has the SHA-256 the id is cut
from."""

from dataclasses import dataclass

from cad.briefs import store as briefs
from cad.briefs.store import BriefRefused
from cad.checks.container import fit
from cad.context_parts.store import confirmed_parts, part_brep
from cad.projects.model import ProjectRefused
from cad.records.roots import Roots
from cad.records.signed import StoreUnusable
from cad.scorecard.model import NoBrief, Scorecard


@dataclass(frozen=True, slots=True)
class Unfitted:
    reason: str


def check_fits(roots: Roots, card: Scorecard) -> tuple[Unfitted, ...]:
    named = sorted({one.instance for one in card.results if one.check_id == fit.ID})
    basis = card.basis
    if not named:
        return ()
    if isinstance(basis, NoBrief):
        return tuple(
            Unfitted(f"the fit result for {one} has no brief to name a project") for one in named
        )
    try:
        project = briefs.read_brief(roots, basis.brief_id).project
        confirmed = {str(part.record.id): part for part in confirmed_parts(roots.projects, project)}
    except (BriefRefused, ProjectRefused, StoreUnusable) as error:
        return (Unfitted(f"cannot read the context parts: {error}"),)
    failures: list[Unfitted] = []
    for one in named:
        part = confirmed.get(one)
        if part is None:
            failures.append(
                Unfitted(f"the fit result for {one} names no part confirmed in project {project}")
            )
            continue
        try:
            part_brep(roots.projects, part)
        except ProjectRefused as error:
            failures.append(Unfitted(str(error)))
    return tuple(failures)
