import time
from typing import Annotated, Final

from pydantic import BaseModel, Field

from cad.auto import building, log
from cad.auto.bounds import bounds_conflicts, unweighed
from cad.auto.gate import gate, record_proposals, stops_at_the_limit, watermark
from cad.auto.model import (
    Asked,
    AutoRun,
    AutoState,
    Event,
    Revised,
    Running,
    RunNotHeld,
    RunRefused,
    RunStopped,
    Standing,
    Started,
    Unsettled,
    nth_run_id,
)
from cad.auto.step import standing_of
from cad.briefs import store as briefs
from cad.briefs.model import MAX_NOTE_CHARS, MadeOf, deciding_check
from cad.context_parts.model import UPDATE_PART
from cad.conversations import store as conversations
from cad.operations import scorecards
from cad.operations.agent_checks import approved_checks
from cad.operations.conversations import ConversationState
from cad.operations.guidance import (
    AUTO_AGENT_CHECKS,
    AUTO_BUILDS,
    AUTO_DESCRIBED,
    BODY_MATERIALS,
)
from cad.operations.model import Audience, Input, Tenant, operation
from cad.operations.variants import (
    MAX_CODE_CHARS,
    BodyMaterials,
    chooser,
    counter,
    with_out_of_date,
)
from cad.sandbox import image
from cad.sandbox.outcome import Built
from cad.scorecard import material
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import BodyChoice, Reason, Slot, code_sha256
from cad.variant_sets.placement import CHOOSE, refuse_unpinned
from cad.variants import entry

SETTLE_SECONDS: Final = 600
AUTO_START = (
    "Start an Auto run on a brief. Call it when a scored option fails a requirement the person "
    "confirmed and a check decides, or that check reads unknown with a reason that says to "
    "change the design, such as a part that bends too far for the stress check to decide. The "
    "run then revises the brief's options until every such requirement passes or the run "
    "stops. Only a web app conversation can start a run, and any "
    "other caller is refused. The start is also refused when the brief has no confirmed "
    "requirement that a check decides, when a proposal on the brief waits for the person, and "
    "after any stop in this conversation until the person writes or answers. A run revises "
    "only against confirmed requirements that a check decides. An assumption and a target that "
    "waits for the person never count. A requirement that an agent-written check the person "
    "approved decides counts. The run uses the confirmed made_of material. When no "
    "requirement names one, you choose it, because the person never does: pass material_key, a "
    "key from list_materials or one of your own for a material the table lacks, and "
    "material_reason, one line saying why it suits the part. Without both the start is "
    "refused. The run builds every revision with that material, records it with the slot as "
    "chosen by the agent, and scores it. When the confirmed targets conflict, the run stops at "
    "once with the proof and builds nothing. not_checked names a pair no check can weigh yet, "
    "such as a mass in a material with no density: tell the person, and research the value. "
    "When this conversation's run on the brief has not "
    "stopped, auto_start returns that run. A run belongs to the conversation that started it: "
    "while it has not stopped, auto_start on its brief from another conversation is refused, "
    "and auto_revise and auto_ask on it are refused from any other conversation and from a "
    "client with no conversation. A conversation holds one run at a time: while its run has "
    "not stopped, starting another brief's run is refused until you stop that run with "
    "auto_ask, and build_variant and score_variant build and score only for the run's brief. "
    + BODY_MATERIALS
)
STOPS = (
    "The run stops when every checked requirement of the latest revision passes, when a "
    "requirement waits on the person, when requirements are proposed in the run's project, "
    "when you call auto_ask, when the person stops it, or when the account's usage limit "
    "refuses a build or a check. Every stop holds the conversation: build_variant, "
    "score_variant, auto_start, auto_revise and auto_ask are refused in it until the person "
    "writes or answers the confirmation page. Give the user the stop's report and start "
    "nothing more. The person can also stop the run with the Stop button in the web app. "
    "build_variant and score_variant take the run from the conversation, so they have no "
    "auto_run argument. "
)
AUTO_REVISE = (
    "Build and score one revision of the design under this conversation's Auto run. Pass "
    "run_id and the build123d code, colours and areas included, with slot as in build_variant: "
    "a slot the run's brief's variant set holds, to revise that variant, or its next free slot. "
    "Any other slot is refused before anything is built, so to revise a variant the person "
    "names, start the run on the brief whose variant set holds it. The server builds the code "
    "into the run's brief's variant set, scores it with the run's material and returns the run. "
    "A running state holds history, one standing per revision with each confirmed "
    "requirement's mark and reasons, why each requirement that fails or is unknown got its mark, "
    "in the deciding check's own words when that check did not pass: revise against those. "
    + AUTO_BUILDS
    + " "
    "Only the check results on the scorecard the server "
    "computed decide a mark, and your own measurements never count. unverified means no check "
    "covers the requirement, and it counts as neither pass nor fail. pass_researched rests on a "
    'researched value: report it as "passes on researched data". '
    + AUTO_AGENT_CHECKS
    + " "
    + AUTO_DESCRIBED
    + " When settling is true, the "
    "latest scorecard still has a pending check and nothing was recorded: call auto_revise "
    "again with the same code to wait for it. Code the run already recorded is not built "
    "again, and nothing new is recorded. Every build and check container is charged to the "
    "account's usage limit, and code the store holds is not built again. A stopped state holds "
    "reason and report: give the user the report. context_parts_out_of_date names the confirmed "
    "context parts that came from an earlier revision of the slot this revision joined: "
    + UPDATE_PART
    + " "
    + STOPS
)
AUTO_ASK = (
    "Stop an Auto run because you need the person: you are stuck, or only the person can "
    "decide, such as which of two conflicting requirements to relax. note says what you tried "
    "and what the person must decide, and names each requirement it is about. The stop's "
    "report gives the note as you wrote it. Returns the stopped run. The stop holds the "
    "conversation until the person writes or answers. On a run that has already stopped, "
    "nothing is recorded and the call is refused."
)
AUTO_STOP = (
    "Stop an Auto run for the person, who pressed Stop in the web app. When the run is its "
    "conversation's current run, the stop holds the conversation, as every stop does: the "
    "agent cannot build, score or start a run in it until the person writes or answers. On a "
    "run that has already stopped, nothing more is recorded. Returns the stopped run and the "
    "conversation's running run and stopped run."
)


class StartInput(Input):
    brief_id: str
    material_key: scorecards.MaterialKey | None = None
    material_reason: Reason | None = None
    materials: BodyMaterials | None = None


class ReviseInput(Input):
    run_id: str
    code: Annotated[str, Field(max_length=MAX_CODE_CHARS)]
    slot: Slot | None = None


class AskInput(Input):
    run_id: str
    note: Annotated[str, Field(min_length=1, max_length=MAX_NOTE_CHARS)]


class StopInput(Input):
    run_id: str


class RevisedRun(AutoRun):
    context_parts_out_of_date: tuple[str, ...] = ()


class PersonStop(BaseModel):
    run: AutoRun
    conversation: ConversationState


def auto_start(tenant: Tenant, arguments: StartInput) -> AutoRun:
    cid = tenant.conversation
    if cid is None:
        raise RunRefused("auto_start needs a web app conversation, and this caller has none")
    roots = tenant.roots
    project = briefs.read_brief(roots, arguments.brief_id).project
    seen = watermark(roots, project)
    latest = briefs.read_state(roots, arguments.brief_id).latest
    if latest is not None and latest.status is briefs.Status.PROPOSED:
        raise RunRefused(
            f"a proposal on brief {arguments.brief_id} waits for the person; start the run "
            "after they answer it"
        )
    confirmed = briefs.confirmed_requirements(roots, arguments.brief_id)
    if confirmed is None or not (
        any(deciding_check(one.target) is not None for one in confirmed.requirements)
        or approved_checks(roots, confirmed)
    ):
        raise briefs.BriefRefused(
            f"brief {arguments.brief_id} has no confirmed requirement that a check decides, "
            "or that an agent-written check the person approved decides, so there is nothing "
            "to revise against"
        )
    pinned = material.pinned_by(confirmed) is not None
    some_pinned = any(isinstance(one.target, MadeOf) for one in confirmed.requirements)
    each = () if pinned else arguments.materials or ()
    single = (arguments.material_key, arguments.material_reason)
    if not some_pinned and not each and None in single:
        raise RunRefused(CHOOSE)
    basis = scorecards.judged(tenant, arguments.brief_id, arguments.material_key, None, each)
    table = basis.table.table
    asked = [(one.body, one.key) for one in arguments.materials or ()]
    refuse_unpinned(material.pins(confirmed, table), asked, table, "Start")
    key = None if each or not (pinned or arguments.material_key) else str(basis.materials_of(()))
    started = Started(
        conversation=cid,
        brief_id=confirmed.brief_id,
        project=project,
        decision_sha256=confirmed.decision_sha256,
        material_key=key,
        material_reason=None if pinned or each else arguments.material_reason,
        watermark=seen,
        conflicts=bounds_conflicts(confirmed.requirements, table),
        not_checked=unweighed(confirmed.requirements, table),
        materials=tuple(
            BodyChoice(body=one.body, key=table.row_key(one.key), reason=one.reason) for one in each
        ),
    )

    def open_under_lock() -> AutoRun:
        number = 1
        while True:
            run_id = nth_run_id(project, confirmed.brief_id, number)
            fresh = not log.exists(roots, run_id)
            if fresh:
                log.create_run(roots, run_id, started)
            run = record_proposals(tenant.roots, tenant.conversations, run_id)
            if fresh or isinstance(run.state, Running):
                if run.state.start.conversation != cid:
                    raise RunNotHeld(
                        f"brief {confirmed.brief_id} has Auto run {run_id} in another "
                        "conversation, which has not stopped; it is not this conversation's run"
                    )
                return run
            number += 1

    return conversations.start_run(
        tenant.roots, tenant.conversations, cid, confirmed.brief_id, open_under_lock
    )


def auto_revise(tenant: Tenant, arguments: ReviseInput) -> RevisedRun:
    _refuse_unless_held(tenant, arguments.run_id)
    with building.building(arguments.run_id, code_sha256(arguments.code)):
        return _revise(tenant, arguments)


def _revise(tenant: Tenant, arguments: ReviseInput) -> RevisedRun:
    roots, run_id = tenant.roots, arguments.run_id
    brief_id = log.read_run(roots, run_id).state.start.brief_id
    running = gate(tenant.roots, tenant.conversations, tenant.bound_run, brief_id)
    assert running is not None
    sha = code_sha256(arguments.code)
    if _tried(running, sha):
        return RevisedRun(run_id=run_id, state=running)
    if arguments.slot is not None:
        variant_sets.refuse_a_slot_out_of_turn(roots, brief_id, arguments.slot)
    revision = len(running.history) + 1
    vid = entry.variant_id(arguments.code, image.image_tag(image.BUILD))
    with stops_at_the_limit(tenant.roots, tenant.conversations, tenant.bound_run, vid):
        start = running.start
        resolve = chooser(
            tenant, brief_id, start.material_key, start.material_reason, start.materials
        )
        built = variant_sets.build_into_set(
            roots,
            tenant.variants,
            brief_id,
            arguments.code,
            arguments.slot,
            resolve,
            on_built=counter(tenant, sha),
        )
        if isinstance(built.outcome, Built):
            scored = scorecards.ScoreVariantInput(
                variant_id=built.variant_id,
                material_key=None if start.materials else start.material_key,
                brief_id=brief_id,
            )
            standing = standing_of(score_until_settled(tenant, scored), revision, sha)
            if isinstance(standing, Unsettled):
                return RevisedRun(run_id=run_id, state=running, settling=True)
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

    run = conversations.record_event(tenant.roots, tenant.conversations, run_id, make)
    stale = with_out_of_date(tenant, brief_id, built).context_parts_out_of_date
    return RevisedRun(
        run_id=run.run_id, state=run.state, settling=run.settling, context_parts_out_of_date=stale
    )


def score_until_settled(
    tenant: Tenant, scored: scorecards.ScoreVariantInput
) -> material.ReportedScorecard:
    """Score again while a check is pending, for up to `SETTLE_SECONDS`, so a revision records
    slow checks such as fea instead of leaving the agent to wait on them. Auto runs only in the
    web app's own chat, which sets no time limit on a tool call. A stop ends the wait, because
    each score refuses a stopped run."""
    deadline = time.monotonic() + SETTLE_SECONDS
    card = scorecards.score_variant(tenant, scored)
    while card.pending and time.monotonic() < deadline:
        card = scorecards.score_variant(tenant, scored)
    return card


def _tried(state: AutoState, sha: str) -> bool:
    return any(one.code_sha256 == sha for one in state.history)


def _refuse_unless_held(tenant: Tenant, run_id: str) -> None:
    if tenant.bound_run != run_id:
        raise RunNotHeld(
            f"auto run {run_id} is not this conversation's Auto run; only the web app "
            "conversation that started it can drive it, until it stops"
        )


def auto_stop(tenant: Tenant, arguments: StopInput) -> PersonStop:
    run_id = arguments.run_id
    run, held = conversations.stop_by_person(
        tenant.roots, tenant.conversations, run_id, lambda state: building.uncounted(run_id, state)
    )
    conversation = ConversationState(
        conversation_id=run.state.start.conversation,
        auto_run=held.auto_run,
        stopped_run=held.stopped_run,
    )
    return PersonStop(run=run, conversation=conversation)


def auto_ask(tenant: Tenant, arguments: AskInput) -> AutoRun:
    _refuse_unless_held(tenant, arguments.run_id)
    run = record_proposals(tenant.roots, tenant.conversations, arguments.run_id)
    if not isinstance(run.state, Running):
        raise RunStopped(run)
    return conversations.record_event(
        tenant.roots, tenant.conversations, arguments.run_id, lambda _: Asked(note=arguments.note)
    )


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
        output=RevisedRun,
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
    operation(
        name="auto_stop",
        audience=Audience.PERSON,
        description=AUTO_STOP,
        input=StopInput,
        output=PersonStop,
        run=auto_stop,
    ),
)
