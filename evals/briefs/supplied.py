"""A card's supplied parts must be the parts its variant's signed build record names, and each must
be a part a person confirmed in the card's project with that BREP (ADR-0012).

The card tells the person which geometry is theirs and that the checks grade only the agent's
body. A row the signed record does not hold, a part the record holds that the card leaves out, or
a row whose BREP no confirmed record of that part has, or whose name or origin is not the
part's newest confirmed record, fails the card. A placement
number on the card resolves to the signed record: the agent chose it, and no check reads it.
"""

from dataclasses import dataclass
from pathlib import Path

from chain import Outcome, PlacedStep, Resolved, Unresolved

from cad.briefs import store as briefs
from cad.briefs.store import BriefRefused
from cad.context_parts.store import stored_parts
from cad.operations.brief_parts import named
from cad.projects.model import ProjectRefused
from cad.records.roots import Roots
from cad.records.signed import StoreUnusable
from cad.sandbox.outcome import PartUse, SandboxUnavailable
from cad.scorecard.model import NoBrief, Scorecard
from cad.scorecard.supplied import Named, SuppliedPart
from cad.variants import entry


@dataclass(frozen=True, slots=True)
class Unsupplied:
    reason: str


type Signed = tuple[PartUse, ...] | None
"""The parts the variant's signed build record names, or None when no signed record is read."""


def signed_parts(root: Path, card: Scorecard) -> Signed:
    try:
        manifest = entry.read_manifest(root, entry.parse_variant_id(card.variant_id))
    except (entry.VariantRefused, SandboxUnavailable):
        return None
    return None if manifest is None else manifest.parts


def check_supplied(roots: Roots, card: Scorecard, signed: Signed) -> tuple[Unsupplied, ...]:
    if not card.supplied and not signed:
        return ()
    if signed is None:
        return (Unsupplied(f"variant {card.variant_id} has no signed record of its parts"),)
    failures = [
        *(_unsigned(card, row, signed) for row in card.supplied if not _signs(row, signed)),
        *(
            Unsupplied(f"the signed build record reads {use.part_id}, which the card leaves out")
            for use in signed
            if not any(_signs(row, (use,)) for row in card.supplied)
        ),
    ]
    return (*failures, *_unconfirmed(roots, card, signed))


def trace_placement(card: Scorecard, signed: Signed, where: tuple[int, int, str, int]) -> Outcome:
    """A number at `supplied[row].placements[place].<axis>[k]` resolves when the signed record of
    that row's part holds the same value there."""
    row, place, axis, k = where
    shown = card.supplied[row]
    use = next((one for one in signed or () if one.part_id == shown.part_id), None)
    if use is None or place >= len(use.placements):
        return Unresolved(f"the signed build record places {shown.part_id} no copy {place + 1}")
    held = use.placements[place].at if axis == "at" else use.placements[place].rotate
    value = (shown.placements[place].at if axis == "at" else shown.placements[place].rotate)[k]
    if held[k] != value:
        return Unresolved(f"the signed build record holds {held[k]:g}, not {value:g}")
    return Resolved((PlacedStep(card.variant_id, shown.part_id),))


def _signs(row: SuppliedPart, signed: tuple[PartUse, ...]) -> bool:
    return any(
        (use.part_id, use.brep_sha256, use.placements)
        == (row.part_id, row.brep_sha256, row.placements)
        for use in signed
    )


def _unsigned(card: Scorecard, row: SuppliedPart, signed: tuple[PartUse, ...]) -> Unsupplied:
    named = next((use for use in signed if use.part_id == row.part_id), None)
    if named is None:
        return Unsupplied(
            f"the card lists {row.part_id}, which the signed build record of {card.variant_id} "
            "does not read"
        )
    return Unsupplied(
        f"the card's row for {row.part_id} is not the BREP and placements the signed build "
        f"record of {card.variant_id} holds"
    )


def _unconfirmed(roots: Roots, card: Scorecard, signed: tuple[PartUse, ...]) -> list[Unsupplied]:
    basis = card.basis
    if isinstance(basis, NoBrief):
        return [Unsupplied("the card lists supplied parts but has no brief to name a project")]
    try:
        project = briefs.read_brief(roots, basis.brief_id).project
        stored = stored_parts(roots.projects, project)
    except (BriefRefused, ProjectRefused, StoreUnusable) as error:
        return [Unsupplied(f"cannot read the project's parts: {error}")]
    failures = [
        Unsupplied(f"the signed build record read {use.part_id} from another project")
        for use in signed
        if use.project != project
    ]
    for row in card.supplied:
        confirmed = [
            one.record
            for one in stored
            if one.outcome == "confirmed" and one.record.id == row.part_id
        ]
        if not any(one.brep_sha256 == row.brep_sha256 for one in confirmed):
            failures.append(
                Unsupplied(
                    f"{row.part_id} with BREP {row.brep_sha256[:12]} is no part confirmed in "
                    f"project {project}"
                )
            )
        elif Named(name=row.name, origin=row.origin) != named(confirmed[-1]):
            failures.append(
                Unsupplied(f"the card's name or origin for {row.part_id} is not its record's")
            )
    return failures
