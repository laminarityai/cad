from collections.abc import Generator
from contextlib import contextmanager

from cad.auto.log import append_event, read_run
from cad.auto.model import AutoRun, Capped, Proposed, Running, RunRefused, RunStopped, Started
from cad.briefs import store as briefs
from cad.conversations.model import Mode
from cad.operations.model import Tenant
from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId
from cad.records.roots import Roots
from cad.sandbox.meter import AccountLimitReached


def gate(tenant: Tenant, brief_id: str | None) -> Running | None:
    """The conversation's own Auto run gates a build or a score. Auto mode with no run refuses."""
    run_id = tenant.auto_run
    if run_id is None:
        if tenant.mode is Mode.AUTO:
            raise RunRefused("this conversation is in Auto mode, so call auto_start first")
        return None
    run = record_proposals(tenant.roots, run_id)
    if not isinstance(run.state, Running):
        raise RunStopped(run)
    start = run.state.start
    if brief_id != start.brief_id:
        raise RunRefused(
            f"auto run {run_id} builds and scores only for brief {start.brief_id}; "
            "pass that brief_id"
        )
    return run.state


@contextmanager
def stops_at_the_limit(roots: Roots, run_id: str | None, variant_id: str) -> Generator[None]:
    """A container under an Auto run that the account's cap refuses stops the run (ADR-0010). The
    meter refuses before the container starts, so nothing is stored for the refused variant."""
    try:
        yield
    except AccountLimitReached as limit:
        if run_id is None:
            raise
        reason = str(limit)
        capped = append_event(roots, run_id, lambda _: Capped(refused=variant_id, reason=reason))
        raise RunStopped(capped) from limit


def record_proposals(roots: Roots, run_id: str) -> AutoRun:
    # Project-wide: one confirmation page lists every brief's waiting items.
    run = read_run(roots, run_id)
    if not isinstance(run.state, Running):
        return run
    fresh = _proposed_since(roots, run.state.start)
    if fresh is None:
        return run
    return append_event(roots, run_id, lambda _: Proposed(requirements=fresh))


def watermark(roots: Roots, project: ProjectId) -> tuple[tuple[str, int], ...]:
    return tuple(
        (brief, len(briefs.read_state(roots, brief).proposals))
        for brief in project_briefs(roots, project)
    )


def _proposed_since(roots: Roots, start: Started) -> tuple[str, ...] | None:
    seen = dict(start.watermark)
    grew = False
    ids: list[str] = []
    for brief in project_briefs(roots, ProjectId(start.project)):
        fresh = briefs.read_state(roots, brief).proposals[seen.get(brief, 0) :]
        grew = grew or bool(fresh)
        ids.extend(one.id for state in fresh for one in state.requirements)
    return tuple(ids) if grew else None
