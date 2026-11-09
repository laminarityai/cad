"""The one check every spending operation makes under an Auto run, before any container starts."""

from cad.auto.log import append_event, read_run
from cad.auto.model import AutoRun, Capped, Proposed, Running, RunRefused, RunStopped, Started
from cad.briefs import store as briefs
from cad.checks.jobs import BuildCharge, Refused
from cad.operations.model import Tenant
from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId
from cad.records.roots import Roots
from cad.sandbox.image import BUILD, image_tag
from cad.variants import entry


def gate(
    tenant: Tenant, run_id: str | None, brief_id: str | None, code: str | None = None
) -> Running | None:
    """None outside a run. Under one: the run as it stands, or RunStopped once it has stopped.
    With code that the store does not hold, the meter is asked for the build, and a refusal
    stops the run; a stored build spends nothing, so it is never refused."""
    if run_id is None:
        return None
    run = observe(tenant.roots, run_id)
    if not isinstance(run.state, Running):
        raise RunStopped(run)
    start = run.state.start
    if brief_id != start.brief_id:
        raise RunRefused(
            f"auto run {run_id} builds and scores only for brief {start.brief_id}; "
            "pass that brief_id"
        )
    if code is not None:
        vid = entry.variant_id(code, image_tag(BUILD))
        if entry.read_manifest(tenant.variants, vid) is None:
            admitted = tenant.meter.admit(BuildCharge(vid))
            if isinstance(admitted, Refused):
                reason = admitted.reason
                capped = append_event(
                    tenant.roots, run_id, lambda _: Capped(refused=vid, reason=reason)
                )
                raise RunStopped(capped)
    return run.state


def observe(roots: Roots, run_id: str) -> AutoRun:
    """The run, after recording any proposal made in its project since it started: all the
    person's waiting items share one page, so a proposal in any brief needs the person."""
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
