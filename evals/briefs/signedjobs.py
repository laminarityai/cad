"""Bind each result on a card the session was shown to the signed job result the server stored
for that card.

A card is not signed. The server keys each job by the variant's shape, the check image and
versions, and the request it sends: the material values it read from the table at the card's
version, and the load case or context part (`cad.checks.jobs.JobSpec.key`). It signs the result
under the variant (`cad.checks.job_store`). A card names its variant, material and table version,
and a background result names its instance, which is the id of its load case (a hash of the
case) or of its context part. So the jobs are planned with the server's own `jobs.plan`, for that
material and that table, with every load case the brief has held (each proposal, each assumption
set and the card's confirmed set) and every part the project confirmed. They are read through
`job_store.read`, which refuses a record the store did not sign. A rescore after research, or
under a new load, keys a new job and leaves the older one on disk, so each card binds to its own.

A shown result must equal its signed result in every field. It carries no verdict exactly when
no target of the card's confirmed set reads its load, as `cad.scorecard.unjudged` reports it.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from chain import Unresolved
from confirmation import REFUSED, Shown

from cad.briefs import assumptions
from cad.briefs import store as briefs
from cad.briefs.model import Target, load_of
from cad.checks import job_store, jobs
from cad.checks.container.wire import LoadCaseWire
from cad.checks.report import build_request
from cad.checks.result import CheckResult
from cad.context_parts.ids import ContextPartId
from cad.context_parts.store import confirmed_parts, part_brep
from cad.records.roots import Roots
from cad.sandbox import image
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard.model import AgainstBrief, AwaitingConfirmation, PendingCheck, Scorecard
from cad.scorecard.unjudged import MeasureOnly, Reported, unconfirmed_loads
from cad.tables.materials import MaterialsTable
from cad.variants import entry

COMPARED = frozenset({"formula", "reason", "sources", "version", "reads", "where"})
"""The fields a shown result must share with its signed result besides its verdict and measures,
which are compared on their own so the reason can name both values."""


@dataclass(frozen=True, slots=True)
class Unsigned:
    """A result on a shown card that no signed job result holds as shown."""

    reason: str


@dataclass(frozen=True, slots=True)
class SignedJobs:
    """The signed results of the jobs a card's own variant, material and table version key, by
    check and instance, and the results the card reports with no verdict. `problem` says why no
    job could be keyed."""

    results: Mapping[tuple[str, str], CheckResult]
    unjudged: frozenset[tuple[str, str]] = field(default_factory=frozenset[tuple[str, str]])
    problem: str | None = None

    def result(self, check_id: str, instance: str) -> CheckResult | Unresolved:
        if self.problem is not None:
            return Unresolved(self.problem)
        held = self.results.get((check_id, instance))
        if held is None:
            return Unresolved(
                f"no signed job result holds {_named(check_id, instance)} for this card's "
                "material and table version"
            )
        return held


def signed_jobs(
    card: Scorecard, root: Path, roots: Roots, table: MaterialsTable, confirmed: Shown | None
) -> SignedJobs:
    """`table` is the table the card was scored against, and `confirmed` the confirmed set its
    basis names, if any."""
    if table.version != card.table_version:
        return SignedJobs({}, problem=f"no table of this brief has version {card.table_version}")
    try:
        held = entry.open_entry(root, card.variant_id, image.image_tag(image.BUILD))
        targets, parts = _history(roots, card, confirmed)
    except (entry.VariantRefused, SandboxUnavailable, *REFUSED) as error:
        return SignedJobs({}, problem=str(error))
    loads: dict[str, LoadCaseWire] = {
        load.id: load.wire() for one in targets if (load := load_of(one)) is not None
    }
    request = build_request(card.material_key, table)
    plan = jobs.plan(root, held, request, table, jobs.Demand(loads=loads, parts=parts))
    results = {
        (one.check_id, one.instance): one
        for job in (plan.quick, *plan.background)
        if (stored := job_store.read(job)) is not None
        for one in stored.results
    }
    judged = () if confirmed is None else [one.target for one in confirmed.requirements]
    return SignedJobs(results, unconfirmed_loads(targets, judged))


def unsigned(card: Scorecard, signed: SignedJobs) -> Iterator[Unsigned]:
    results: Sequence[Reported] = card.results
    for shown in results:
        if isinstance(shown, PendingCheck):
            continue
        held = signed.result(shown.check_id, shown.instance)
        named = _named(shown.check_id, shown.instance)
        if isinstance(held, Unresolved):
            yield Unsigned(held.reason)
            continue
        verdict = _misjudged(shown, held, (shown.check_id, shown.instance) in signed.unjudged)
        if verdict is not None:
            yield Unsigned(f"the card shows {named} {verdict}")
        names = [one.name for one in shown.measured]
        held_names = [one.name for one in held.measured]
        if names != held_names:
            yield Unsigned(
                f"the card's {named} measures {_list(names)}, but the signed job result "
                f"measures {_list(held_names)}"
            )
        ours = shown.model_dump(mode="json", include=set(COMPARED))
        theirs = held.model_dump(mode="json", include=set(COMPARED))
        differs = sorted(name for name in COMPARED if ours.get(name) != theirs.get(name))
        if differs:
            yield Unsigned(
                f"the card's {named} differs from the signed job result in {', '.join(differs)}"
            )


def _history(
    roots: Roots, card: Scorecard, confirmed: Shown | None
) -> tuple[list[Target], dict[ContextPartId, jobs.PartBrep]]:
    """Every target whose load the card's brief has held, and every part its project confirmed."""
    basis = card.basis
    if not isinstance(basis, AgainstBrief | AwaitingConfirmation):
        return [], {}
    state = briefs.read_state(roots, basis.brief_id)
    targets = [
        *(one.target for held in state.proposals for one in held.proposal.requirements),
        *(
            one.target
            for held in assumptions.every_set(roots, basis.brief_id)
            for one in held.assumptions
        ),
        *(() if confirmed is None else (one.target for one in confirmed.requirements)),
    ]
    project = state.brief.project
    parts = {
        part.record.id: jobs.PartBrep(part.record.brep_sha256, part_brep(roots.projects, part))
        for part in confirmed_parts(roots.projects, project)
    }
    return targets, parts


def _named(check_id: str, instance: str) -> str:
    return f"{check_id} for {instance}" if instance else check_id


def _misjudged(shown: CheckResult | MeasureOnly, held: CheckResult, unjudged: bool) -> str | None:
    """How the card's verdict differs from the one the server shows for the signed result."""
    if isinstance(shown, MeasureOnly):
        if unjudged:
            return None
        return (
            f"with no verdict, but a target the card's confirmed set holds reads its load, "
            f"so the server shows its signed verdict {held.verdict}"
        )
    if unjudged:
        return (
            f"{shown.verdict}, but no target the card's confirmed set holds reads its load, "
            "so the server shows it with no verdict"
        )
    if shown.verdict != held.verdict:
        return f"{shown.verdict}, but its signed job result holds {held.verdict}"
    return None


def _list(names: Sequence[str]) -> str:
    return ", ".join(names) if names else "nothing"
