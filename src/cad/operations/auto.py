from typing import Annotated, Final

from pydantic import Field

from cad.auto import log
from cad.auto.bounds import bounds_conflicts
from cad.auto.gate import gate, record_proposals, stops_at_the_limit, watermark
from cad.auto.model import (
    Asked,
    AutoRun,
    AutoState,
    Event,
    Revised,
    Running,
    RunRefused,
    Standing,
    Started,
    Unsettled,
    nth_run_id,
)
from cad.auto.step import standing_of
from cad.briefs import store as briefs
from cad.briefs.model import MAX_NOTE_CHARS, MadeOf
from cad.operations import scorecards
from cad.operations.model import Audience, Input, Mode, Tenant, operation
from cad.operations.variants import MAX_CODE_CHARS
from cad.sandbox import image
from cad.sandbox.outcome import Built
from cad.scorecard import material
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import code_sha256
from cad.variants import entry

AUTO_START = (
    "Start an Auto run on a brief whose requirements the person confirmed. Only a conversation "
    "the person switched to Auto mode in the web app can start one; any other caller is "
    "refused. The run uses the confirmed made_of material, or material_key when no requirement "
    "names one. When the confirmed targets conflict, the run stops at once with the proof and "
    "builds nothing. A brief that already has a run that has not stopped returns that run."
)
STOPS = (
    "The run stops when every checked requirement of the latest revision passes, when a "
    "requirement waits on the person, when requirements are proposed in the run's project, "
    "when you call auto_ask, or when the account's usage limit refuses a build or a check. Once "
    "it has "
    "stopped, auto_revise, and build_variant and score_variant with its auto_run, are refused "
    "before anything builds or runs: give the user the stop's report and start nothing more. "
)
AUTO_REVISE = (
    "Build and score one revision of the design under an Auto run the person started. Pass "
    "run_id and the build123d code, with slot as in build_variant. The server builds the code "
    "into the run's brief's variant set, scores it with the run's material and returns the run. "
    "A running state holds history, one standing per revision with each confirmed "
    "requirement's mark, and failing, the requirements of the latest revision that fail or are "
    "unknown: revise against those. Only the check results on the scorecard the server "
    "computed decide a mark, and your own measurements never count. unverified means no check "
    "covers the requirement, and it counts as neither pass nor fail. pass_researched rests on a "
    'researched value: report it as "passes on researched data". When settling is true, the '
    "latest scorecard still has a pending check and nothing was recorded: call auto_revise "
    "again with the same code to wait for it. Code the run already recorded is not built "
    "again, and nothing new is recorded. Every build and check container is charged to the "
    "account's usage limit, and code the store holds is not built again. A stopped state holds "
    "reason and report: give the user the report. " + STOPS
)
AUTO_ASK = (
    "Stop an Auto run because you need the person: you are stuck, or only the person can "
    "decide, such as which of two conflicting requirements to relax. note says what you tried "
    "and what the person must decide, and names each requirement it is about. The stop's "
    "report gives the note as you wrote it. Returns the stopped run. On a run that has "
    "already stopped, nothing is recorded and the existing stop is returned."
)


class StartInput(Input):
    brief_id: str
    material_key: scorecards.MaterialKey | None = None


class ReviseInput(Input):
    run_id: str
    code: Annotated[str, Field(max_length=MAX_CODE_CHARS)]
    slot: Annotated[int | None, Field(strict=True)] = None


class AskInput(Input):
    run_id: str
    note: Annotated[str, Field(min_length=1, max_length=MAX_NOTE_CHARS)]


def auto_start(tenant: Tenant, arguments: StartInput) -> AutoRun:
    if tenant.mode is not Mode.AUTO:
        raise RunRefused(
            "auto_start needs a web app conversation the person switched to Auto mode; "
            f"this caller's mode is {tenant.mode or 'none'}"
        )
    roots = tenant.roots
    confirmed = briefs.confirmed_requirements(roots, arguments.brief_id)
    if confirmed is None:
        raise briefs.BriefRefused(
            f"brief {arguments.brief_id} has no confirmed requirements; Plan mode comes first"
        )
    pin = material.pinned_by(confirmed)
    named = pin.target.material if pin is not None and isinstance(pin.target, MadeOf) else None
    key = arguments.material_key or named
    if key is None:
        raise RunRefused("no confirmed requirement names the material, so pass material_key")
    basis = scorecards.judged(tenant, arguments.brief_id, key)
    project = briefs.read_brief(roots, arguments.brief_id).project
    started = Started(
        brief_id=confirmed.brief_id,
        project=project,
        decision_sha256=confirmed.decision_sha256,
        material_key=basis.material_key,
        watermark=watermark(roots, project),
        conflicts=bounds_conflicts(confirmed.requirements, basis.table.table),
    )
    number = 1
    while True:
        run_id = nth_run_id(project, confirmed.brief_id, number)
        existed = log.exists(roots, run_id)
        if not existed:
            log.create_run(roots, run_id, started)
        run = record_proposals(roots, run_id)
        # A start that lost the create to a concurrent one returns the winner's run.
        if isinstance(run.state, Running) or not existed:
            return run
        number += 1


def auto_revise(tenant: Tenant, arguments: ReviseInput) -> AutoRun:
    roots, run_id = tenant.roots, arguments.run_id
    brief_id = log.read_run(roots, run_id).state.start.brief_id
    running = gate(tenant, run_id, brief_id)
    assert running is not None
    sha = code_sha256(arguments.code)
    if _tried(running, sha):
        return AutoRun(run_id=run_id, state=running)
    revision = len(running.history) + 1
    vid = entry.variant_id(arguments.code, image.image_tag(image.BUILD))
    with stops_at_the_limit(roots, run_id, vid):
        built = variant_sets.build_into_set(
            roots, tenant.variants, brief_id, arguments.code, arguments.slot
        )
        if built.outcome == Built():
            scored = scorecards.ScoreVariantInput(
                variant_id=built.variant_id,
                material_key=running.start.material_key,
                brief_id=brief_id,
            )
            standing = standing_of(scorecards.score_variant(tenant, scored), revision, sha)
            if isinstance(standing, Unsettled):
                return AutoRun(run_id=run_id, state=running, settling=True)
        else:
            standing = Standing(
                revision=revision,
                variant_id=built.variant_id,
                code_sha256=sha,
                built=False,
                marks=(),
            )

    def make(state: Running) -> Event | None:
        if _tried(state, sha):
            return None
        return Revised(standing=standing.model_copy(update={"revision": len(state.history) + 1}))

    return log.append_event(roots, run_id, make)


def _tried(state: AutoState, sha: str) -> bool:
    return any(one.code_sha256 == sha for one in state.history)


def auto_ask(tenant: Tenant, arguments: AskInput) -> AutoRun:
    record_proposals(tenant.roots, arguments.run_id)
    return log.append_event(tenant.roots, arguments.run_id, lambda _: Asked(note=arguments.note))


OPERATIONS: Final = (
    operation(
        name="auto_start",
        audience=Audience.AGENT,
        description=AUTO_START,
        input=StartInput,
        output=AutoRun,
        run=auto_start,
    ),
    operation(
        name="auto_revise",
        audience=Audience.AGENT,
        description=AUTO_REVISE,
        input=ReviseInput,
        output=AutoRun,
        run=auto_revise,
    ),
    operation(
        name="auto_ask",
        audience=Audience.AGENT,
        description=AUTO_ASK,
        input=AskInput,
        output=AutoRun,
        run=auto_ask,
    ),
)
