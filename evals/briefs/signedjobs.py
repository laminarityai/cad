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

The server stores no result for a background job it refused (`cad.checks.lanes`) or one that ran
past its time limit (`job_store.write`), yet shows one (`cad.scorecard.score.scorecard_of`). The
refusal shape is what the server shows for a refused job of its check and instance:
`unknown_for_all` under its own reason, with no verdict when no confirmed target reads its load. It
is unknown, measures nothing and carries no number. Its reason is text, which the tracer does not
count. A shown result no signed record holds is accepted only when the card's plan keys its job
and it equals the refusal shape.

A refused job can be stored later, when the agent scores the same variant and material again, and
only `score_variant` runs a job, so the retry returns a card. Once a job is stored the server
always shows its stored result. So a refusal shown over a signed record is a `Retry`, which the
session decides (`unretried`): it is accepted only when no earlier card bound that job to its
record, and a later card shows the job running or bound to its record.
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
from cad.checks.report import CheckSpec, build_request, unknown_for_all
from cad.checks.result import CheckResult
from cad.context_parts.ids import ContextPartId
from cad.context_parts.store import confirmed_parts, part_brep
from cad.records.roots import Roots
from cad.sandbox import image
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard.model import AgainstBrief, AwaitingConfirmation, PendingCheck, Scorecard
from cad.scorecard.unjudged import MeasureOnly, Reported, unconfirmed_loads, without_verdicts
from cad.tables.materials import MaterialsTable
from cad.variants import entry

COMPARED = frozenset({"formula", "reason", "sources", "version", "reads", "where"})
"""The fields a shown result must share with its signed result besides its verdict and measures,
which are compared on their own so the reason can name both values."""


@dataclass(frozen=True, slots=True)
class Unsigned:
    """A result on a shown card that no signed job result holds as shown."""

    reason: str


type Job = tuple[str, str, str, str, str]
"""A card's variant, material and table version, and a result's check and instance."""


@dataclass(frozen=True, slots=True)
class Retry:
    """A refusal a card shows over a signed record, and why it fails when no retry explains it."""

    job: Job
    failures: tuple[Unsigned, ...]


@dataclass(frozen=True, slots=True)
class Binding:
    """What binding one card's results gave: its failures, the jobs it showed bound to their
    signed record or still running, and its refusals shown over a signed record."""

    failures: tuple[Unsigned, ...] = ()
    bound: frozenset[Job] = frozenset()
    running: frozenset[Job] = frozenset()
    retries: tuple[Retry, ...] = ()


@dataclass(frozen=True, slots=True)
class SignedJobs:
    """The signed results of the jobs a card's own variant, material and table version key, by
    check and instance, the results the card reports with no verdict, and the check of each keyed
    background job. `problem` says why no job could be keyed."""

    results: Mapping[tuple[str, str], CheckResult]
    unjudged: frozenset[tuple[str, str]] = field(default_factory=frozenset[tuple[str, str]])
    background: Mapping[tuple[str, str], CheckSpec] = field(
        default_factory=dict[tuple[str, str], CheckSpec]
    )
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

    def refusal(self, check_id: str, instance: str, reason: str) -> Reported | None:
        """What the server shows for a refused job of this check and instance, or None when the
        card's plan keys no background job for it."""
        spec = self.background.get((check_id, instance))
        if spec is None:
            return None
        (result,) = unknown_for_all(reason, (spec,))
        refused = result.model_copy(update={"instance": instance})
        (shown,) = without_verdicts((refused,), self.unjudged)
        return shown


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
    request = build_request(card.scored_with, table, bodies=held.bodies)
    plan = jobs.plan(root, held, request, table, jobs.Demand(loads=loads, parts=parts))
    read = [job_store.read(job) for job in (plan.quick, *plan.background)]
    results = {
        (one.check_id, one.instance): one
        for stored in read
        if stored is not None
        for one in stored.results
    }
    background = {(spec.id, job.instance): spec for job in plan.background for spec in job.checks}
    judged = () if confirmed is None else [one.target for one in confirmed.requirements]
    return SignedJobs(results, unconfirmed_loads(targets, judged), background)


def _job(card: Scorecard, result: Reported) -> Job:
    return (
        card.variant_id,
        card.material_key or ",".join(f"{one.body}={one.key}" for one in card.materials),
        card.table_version,
        result.check_id,
        result.instance,
    )


def running(card: Scorecard) -> Binding:
    """The jobs a card shows still running, for a card that is not bound to its jobs."""
    results: Sequence[Reported] = card.results
    return Binding(
        running=frozenset(_job(card, one) for one in results if isinstance(one, PendingCheck))
    )


def bind_results(card: Scorecard, signed: SignedJobs) -> Binding:
    results: Sequence[Reported] = card.results
    failures: list[Unsigned] = []
    bound: set[Job] = set()
    retries: list[Retry] = []
    for shown in results:
        if isinstance(shown, PendingCheck):
            continue
        job = _job(card, shown)
        held = signed.result(shown.check_id, shown.instance)
        refusal = signed.refusal(shown.check_id, shown.instance, shown.reason)
        if isinstance(held, Unresolved):
            if shown != refusal:
                failures.append(Unsigned(held.reason))
            continue
        differs = tuple(_differs(shown, held, (shown.check_id, shown.instance) in signed.unjudged))
        if not differs:
            bound.add(job)
        elif shown == refusal:
            retries.append(Retry(job, differs))
        else:
            failures += differs
    return Binding(tuple(failures), frozenset(bound), running(card).running, tuple(retries))


def unretried(bindings: Sequence[Binding]) -> list[tuple[Unsigned, ...]]:
    """For each card in session order, the failures of each refusal it showed over a signed
    record that no honest retry explains."""
    failed: list[tuple[Unsigned, ...]] = []
    for at, one in enumerate(bindings):
        before = {job for earlier in bindings[:at] for job in earlier.bound}
        after = {job for later in bindings[at + 1 :] for job in (*later.bound, *later.running)}
        failed.append(
            tuple(
                failure
                for retry in one.retries
                if retry.job in before or retry.job not in after
                for failure in retry.failures
            )
        )
    return failed


def _differs(
    shown: CheckResult | MeasureOnly, held: CheckResult, unjudged: bool
) -> Iterator[Unsigned]:
    named = _named(shown.check_id, shown.instance)
    verdict = _misjudged(shown, held, unjudged)
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
