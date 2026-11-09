# Phase 4 design: the web app

Status: proposed on 2026-11-08. Nothing in it is built. It was written against commit 2bc3648. Terms follow GLOSSARY.md. Each phase 4 PR is one numbered unit of §4. §7 lists the questions only the operator can answer.

The operator made these decisions on 2026-11-08, and this revision records them. ADR-0010 (templates) and the Auto mode ADR, now ADR-0011, are approved. The warm per-account zygote is dropped as too costly for an MVP, so builds stay a fresh container per build. SPEC's phase 4 exit no longer has a time target. Accounts and usage limits move from phase 3 to phase 4. A passkey ADR was declined. Hosted confirmation follows the operator's 2026-11-07 direction in #47, recorded as an amendment to ADR-0004 that still needs approval (§4, unit 0).

Phase 4 in SPEC: chat, 3D viewer, scorecards, sliders, the mode switcher, Auto mode with its stopping rules, and accounts with usage limits. Exit: releasing a slider rebuilds the variant and updates its scorecard without a page reload, and Auto mode stops correctly on a brief whose requirements conflict.

## What the design starts from

These facts about main shape the design. Each was read in code or measured.

- The server speaks MCP over stdio only (`server/__main__.py`). It has no HTTP API, no accounts, no geometry export tool and no read tool for a variant set or a stored scorecard.
- A variant is opaque agent Python. Its id is a hash of the build image tag, `TRUST_DIGEST` and the code (`variants/entry.py:73`). Nothing in it can be tuned.
- Every build is a fresh `docker run`. Measured on a Mac with Docker Desktop and a warm image: importing build123d in a fresh container takes 2.5 to 3.2 s, and an uncached `build_variant` takes 4.5 to 5.9 s end to end. Phase 4 keeps this path (§5).
- Confirmation is a 127.0.0.1 page with a one-time token in the URL, held in an in-memory `Desk` (ADR-0004). A hosted server cannot open it. A link in a tool result would let the agent confirm itself (#47).
- Claude Code 2.1.287 opens a server's URL for the person through MCP URL-mode elicitation, and the model never sees the URL. This was tested on 2026-11-08 with a one-tool server on mcp 2.3.0 (§2.4).
- The scorecard is written unsigned to `scorecard.json` and never read back. It is also written twice (#105).
- Modes are instruction text. Auto mode has no code.
- Accounts and usage limits were planned for phase 3, but the phase 3 design has no unit for them, and none are built. SPEC now places them in phase 4. `Meter` exists as a seam, wired to `Unmetered` (`checks/jobs.py`).

## Central decisions

1. **One operation registry, two adapters, and an audience on every operation.** Every capability is one typed `Operation` in `cad/operations/`. The MCP tool list and the HTTP routes are both generated from that list. An operation marked `PERSON` only, such as answering the confirmation page or moving a slider, has no MCP tool at all. So "the agent cannot confirm" is a property of the registry, not of a check someone must remember. ADR-0002 still holds, because the web app's agent uses the same MCP tools as any outside client.
2. **A template is code with a declared `PARAMS` literal, and a tuned variant is the same code with a different literal.** The server reads and rewrites the literal through `ast` and never runs agent code on the host. A tuned variant is therefore an ordinary variant, with the id, store, scorecard and checks that already exist. There is one identity scheme.
3. **A person confirms with the Confirm button in the signed-in web app.** This is the operator's direction in #47 (2026-11-07). An amendment to ADR-0004 records it and keeps that ADR's rules: only the page's handler writes the answer, and status is derived from signed records. An outside MCP client signs the person in with MCP authorization, as any remote MCP server does. If the client supports URL-mode elicitation, `ask_to_confirm` asks it to open the page for the person. Otherwise the tool says the proposal is waiting in the web app. On neither path does the agent get a link or a token. The limit stays the one ADR-0003 and ADR-0004 already accept: a process that drives the person's signed-in browser could press the button.
4. **The server decides when Auto mode stops.** The web backend runs the LLM turns. The stopping rules are a pure function over the signed scorecards of the run, held in a signed per-run log on the server. Once a run is stopped, `build_variant` and `score_variant` under that run are refused before any container starts. A bug in our client cannot spend past a stop.
5. **Phase 4 takes on accounts and usage limits.** The Confirm button needs a signed-in person, and a hosted app needs tenancy, so the operator moved them from phase 3 to phase 4 on 2026-11-08. Phase 4 runs one replica.

## 1. Usage (caller's view)

### 1a. The agent declares a template

```python
build_variant(
    code="""
from build123d import *
PARAMS = {
    "length": {"value": 80, "min": 40, "max": 160, "step": 0.5, "unit": "mm"},
    "wall":   {"value": 3,  "min": 1.2, "max": 8,  "step": 0.1, "unit": "mm"},
}
p = {k: v["value"] for k, v in PARAMS.items()}
result = Box(p["length"], 40, 20) - Box(p["length"] - 2 * p["wall"], 40 - 2 * p["wall"], 20)
""",
    brief_id="b-…",
)
# -> {variant_id, outcome, parameters: [{name: "length", …}, {name: "wall", …}], variant_set: {slot: 2}}
```

Code with no `PARAMS` is a template with no parameters and shows no sliders. The agent's bounds decide no check, so letting it set them grades nothing.

### 1b. The person tunes a member in the browser

```ts
const set = await api.variantSet(projectId, briefId);         // VariantSetView, types generated from Python
const card = api.scorecardStream(variantId);                    // SSE, each event a whole ScorecardSnapshot
slider.onRelease(v => api.tune(memberRef, { wall: v }));       // one build per release, latest wins
events.on("variant_built", e => viewer.replace(e.view));       // no reload; the time is recorded, not gated
```

### 1c. The web backend runs Auto mode

```python
run = await mcp.call("auto_start", brief_id=b)  # Continue | Stopped, Bounds conflicts stop here
while isinstance(run, Continue):
    run = await mcp.call("auto_revise", run_id=run.run_id, code=await llm.revise(run.failing))
chat.post(run.report)  # server-written: reason, requirements, revisions tried
```

The agent may call `auto_ask(note)` at any time to stop early. It can always stop a run and can never keep one going.

## 2. Shape

### 2.1 Operations (`cad/operations/`)

```python
class Audience(Flag):
    AGENT = auto()
    PERSON = auto()


@dataclass(frozen=True, slots=True)
class Operation[I: BaseModel, O: BaseModel]:
    name: str
    audience: Audience
    input: type[I]
    output: type[O]
    run: Callable[[Tenant, Principal, I], O]


OPERATIONS: Final[tuple[Operation, ...]]
```

- `AGENT`: `build_variant`, `score_variant`, `propose_requirements`, `submit_research`, `ask_to_confirm`, `auto_start`, `auto_revise`, `auto_ask`.
- `PERSON`: `answer_page`, `tune`, `set_mode`.
- Both: `list_projects`, `project`, `brief`, `variant_set`, `scorecard`, `view`, `search_knowledge`, `list_materials`, `server_info`.

`server/app.py` stops building `Tool` objects by hand. The existing tools move into the registry in the same PR, and the hand registration is deleted. A test fails if any MCP tool, HTTP route or generated TypeScript type does not come from a registry entry. The adapters parse a `Principal` at the boundary and pass a `Tenant`, so core code never reads module-level roots such as `entry.VARIANTS_ROOT`.

### 2.2 Templates (`cad/templates/`)

```python
class Param(_Frozen):
    value: float
    min: float
    max: float
    step: float
    unit: Literal["mm", "deg", "count"]
    # validator: min <= value <= max, step > 0, at most 12 per template


def declared(code: str) -> Mapping[ParamName, Param] | NoParams | ParamsRefused: ...  # ast only
def rewrite(code: str, values: Mapping[ParamName, float]) -> str | ParamsRefused:
    ...
    # snaps each value to step, refuses unknown names and out-of-range values,
    # replaces only the PARAMS literal's source span
```

Snapping to `step` makes a release at an earlier value a store hit with no build, per make-operations-idempotent. A dead parameter is detectable, because its tuned BREP hash equals the base's. The scorecard can then say that the slider changes nothing.

A variant-set member keeps its slot and points at its current variant:

```python
class Member(_Frozen):
    slot: int  # 1..5, unchanged by tuning
    head: VariantId  # what the viewer and scorecard show
    set_by: Mapping[ParamName, Literal["agent", "person"]]


class Tuning(_Frozen):  # signed, append-only, one per settled change of head
    member: MemberRef
    values: Mapping[ParamName, float]
    variant_id: VariantId
    by: Literal["agent", "person"]
```

Moving `head` is not a confirmation, so either actor may do it. `set_by` is how Auto mode knows "something the person set" (§2.5). The SPEC's "git per design" maps onto this log: a member is a branch and a tuning is a commit. Phase 4 does not run git (§5).

### 2.3 Slider builds

A tune builds the rewritten code through `build_variant`'s existing path: a fresh `docker run` per build, with the limits `container.Job` already sets. There is one build path, and a tuned variant gets no special treatment.

The front end sends one tune per release, never per drag tick, so a drag starts no container. If the person releases again while a build runs, the latest value wins and the server drops the earlier tune if its build has not started. A value tried before is a store hit with no build (§2.2).

The time from release to the new mesh is recorded in each tune's result and is not gated. On the measured path an uncached build takes 4.5 to 5.9 s.

Tessellation runs as a job in the analysis image (ADR-0005), never in an agent process, so the viewer shows exactly the BREP the checks measured. It runs next to the quick job (closed solid, interference, mass, extents). Release plans the full job set. Every row turns pending. The previous number may show as ghost text labelled "before", with no verdict colour, because the type of a pending row has no verdict field. A check job for a superseded head is dropped from the queue if it has not started. If it has started, it finishes and is cached.

### 2.4 Confirmation (amends ADR-0004, resolves #47)

```python
type Principal = PersonSession | AgentToken


class PersonSession(_Frozen):
    kind: Literal["person"] = "person"
    account: AccountId
    session_id: str


class AgentToken(_Frozen):
    kind: Literal["agent"] = "agent"
    account: AccountId
    token_id: str
    conversation: ConversationId | None
    auto_run: AutoRunId | None
    mode: Mode
```

A person session comes only from an HttpOnly, Secure, SameSite=Strict cookie that sign-in sets. An agent token comes only from an `Authorization: Bearer` header on `/mcp`. Different FastAPI dependencies parse them, and `answer_page` is `PERSON` only, so no MCP tool can answer a page.

**How an outside client reaches the page.** The operator wants a person in Claude Code, or any MCP client, to reach the confirmation as with any other remote MCP server. Two parts of the MCP spec do that, and phase 4 uses both.

1. **Sign-in is MCP authorization.** The [authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) makes the server an OAuth 2.1 resource server. It serves Protected Resource Metadata (RFC 9728), and the client opens the person's browser for sign-in with PKCE and a `resource` indicator (RFC 8707). Our server is also the authorization server, and its sign-in page is the web app's magic link. The access token it issues is the `AgentToken`, audience-bound to `/mcp`. In Claude Code the person runs `/mcp` or `claude mcp login cad` once ([Claude Code MCP docs](https://code.claude.com/docs/en/mcp)). Nobody pastes a token.
2. **The page opens through URL-mode elicitation.** In [URL mode](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation) the server asks the client to open a URL for the person. The client must show the full URL and ask consent before it opens it, and it must open it so that neither the client nor the model can read the page. The answer is out of band. `accept` means only that the person agreed to open the URL. If the client declared `elicitation.url`, `ask_to_confirm` returns an `InputRequiredResult` that asks it to open `https://<app>/projects/<pid>/confirm`. On a 2025-11-25 connection it sends `elicitation/create` with `mode: "url"` instead. The mcp 2.3.0 SDK does both. When the client retries, the tool waits at most 20 s for the signed `PageAnswer`, as today, then returns `waiting`.

The URL carries no token and no answer. It is the page's ordinary address in the app, so it grants nothing without the person's session cookie, and the spec forbids a pre-authenticated URL anyway. The page checks that the session's account is the account of the `AgentToken` that asked, as the spec's phishing rule requires. Status still comes only from the signed `PageAnswer` that the page's handler writes. The server never reads the client's `accept`, `decline` or `cancel` as an answer. Whichever of the three arrives, the tool reports what the signed records say, so a hook that answers the elicitation changes nothing.

This keeps ADR-0004 and #47. ADR-0004 rejected form-mode elicitation because an `Elicitation` hook could answer the form, and that answer was the decision. Here the hook can only accept or decline opening a page. #47 says an outside client gets no link or token, because a link in a tool result lets the agent open it. The tool result still has none. The URL goes to the person through the client's own dialog, and the model never sees it. A process that can drive the person's signed-in browser could still press Confirm, which is the limit ADR-0003 and ADR-0004 already accept.

**Tested on 2026-11-08** with a one-tool server on mcp 2.3.0 and Claude Code 2.1.287, on the 2026-07-28 protocol. Claude Code declared `elicitation: {form, url}`. In an interactive session it showed "MCP server wants to open a URL" with the message, the full URL, and Accept and Decline. Decline reached the server as `action: "decline"`. Under `claude -p` the elicitation came back as `cancel`. The model's transcript did not contain the URL. An `Elicitation` hook did receive the URL. That is harmless, because the URL grants nothing. The [changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) adds URL mode for 2026-07-28 connections in 2.1.281 and for 2025-11-25 connections in 2.1.287. Earlier versions were reported to drop the capability ([#69555](https://github.com/anthropics/claude-code/issues/69555), [#88075](https://github.com/anthropics/claude-code/issues/88075)). An issue reported that the VS Code extension declined URL elicitation ([#35353](https://github.com/anthropics/claude-code/issues/35353), now closed). This design did not test the extension.

**Fallback.** A client that does not declare `elicitation.url`, a headless run, and a person who declines all get the same result: `ask_to_confirm` returns `waiting in the web app`, with no link and no token. The person opens the web app, where every waiting item in the project is on the page. The agent's next call reads the signed answer.

**Onshape.** The Onshape Confirm button from #47 waits for the Onshape extension panel, which SPEC lists as out of scope. Until then, Onshape users confirm in the web app.

The page keeps the `ItemKind` registry, `answers.py` and its sections unchanged. FastAPI renders it inside the signed-in app in place of the stdlib server. Its form carries a CSRF token bound to the page snapshot, so "an item added after the page opened records nothing" still holds. `PageAnswer` gains `account` and `session_id`, and the projects key still signs it. The stdlib `ThreadingHTTPServer` page and the in-memory `Desk` are deleted.

Local dev and the eval driver run the same FastAPI app on 127.0.0.1. With `--opener PROGRAM`, the server mints a local person session and hands its sign-in link only to that program, as it hands the page URL today. One page and one answer record serve both.

### 2.5 Auto mode (`cad/auto/`, ADR-0011)

```python
class Standing(_Frozen):  # one settled revision, projected from a scorecard
    revision: int
    variant_id: VariantId | None  # None: the build failed, which counts as no progress
    margin: Mapping[RequirementId, float | None]
    # in [-1, 1]. For <=: (limit - m) / (|limit| + |m|). For >=: (m - limit) / (|limit| + |m|).
    # The sign is the verdict. The minimum over a requirement's comparisons.
    # None: unknown, unverified, waiting or pending. No number means no progress.


type StopReason = AllPass | NeedsPerson | Stalled


class NeedsPerson(_Frozen):
    kind: Literal["conflict", "person_set_value", "source_to_confirm", "agent_asked"]
    requirements: tuple[RequirementId, ...]
    evidence: ConflictEvidence | None
    note: str


type ConflictEvidence = Bounds | Tradeoff


class Bounds(_Frozen):  # proved from confirmed targets and tables, before any build
    statement: str  # "min_mass 50 g > density(PLA) 1.24 g/cm³ × envelope 8 cm³ = 9.9 g"
    reads: tuple[Read, ...]  # table rows by exact key, researched rows labelled


class Tradeoff(_Frozen):  # observed in the run
    best_a: VariantId
    best_b: VariantId  # each is the best for one requirement, and no revision passes both


class Running(_Frozen):
    history: tuple[Standing, ...]
    best: Mapping[RequirementId, float]
    stale: int


class Stopped(_Frozen):
    history: tuple[Standing, ...]
    reason: StopReason
    report: str


type AutoState = Running | Stopped


def bounds_conflicts(reqs: ConfirmedRequirements, tables: Tables) -> tuple[Conflict, ...]: ...
def step(state: Running, standing: Standing) -> AutoState: ...
```

The rules, in order:

1. **Bounds conflict.** `auto_start` runs `bounds_conflicts` before any build. It is interval arithmetic over the kinds that bound one quantity. Mass is bounded by `min_mass`, `max_mass`, and `made_of` density times the `envelope` volume. Extent is bounded by `envelope` and `measure_limit`. It also runs when the person opens the confirmation page, so Plan mode warns before anything is built.
2. **All pass.** Every `Checked` requirement passes. `Unverified` requirements are listed in the stop report and count as neither pass nor fail, or Auto could never end on a brief with an unchecked requirement. A pass that rests on research is reported as "passes on researched data" (ADR-0009).
3. **Needs the person.** A tool call under the run that changes a parameter whose `set_by` is `person`, or that proposes requirements, stops the run. So does a latest scorecard row that is `Waiting` on a confirmation. The agent's `auto_ask` also stops it.
4. **Stalled or traded off.** A revision makes progress when some failing requirement's margin beats its best earlier in the run by at least δ = 0.02. Comparing against the best, not the previous revision, means oscillating between two requirements earns nothing. Three revisions in a row without progress stop the run. If two failing requirements have different best revisions and no revision passes both, the reason is `NeedsPerson(conflict, Tradeoff)`, which asks which one to relax. Otherwise it is `Stalled`, with what was tried.

A revision counts only once its scorecard has no pending check. The server waits for settlement, so a slow FEA job is never a revision without progress. `standing` reads only `AgainstBrief.requirements` and `Checked` rows, so an agent measurement (ADR-0008) has no path into the rules, and a test asserts that.

**Termination.** Margins lie in [-1, 1], and each requirement's best only rises. Each reset of the stall counter uses up at least δ of that range, so a run has at most `3 × 2/δ = 300` revisions per failing requirement. A property test generates adversarial scorecard sequences and asserts the bound. Together with the server refusing builds after a stop, this answers the SPEC risk that a stuck-detection bug spends without limit. It adds no budget.

State lives in an append-only signed log at `projects/<pid>/auto/<run>/NNNN.signed`. `AutoState` is a fold over that log, never a stored field, as brief status already is. Replaying `auto_revise` with the same code gives the same variant id, which is already in the log, so it returns the same state without appending.

**Modes** are conversation state. `set_mode` is `PERSON` only. Our backend mints a short-lived agent token for each turn, and the token carries the mode. Under Plan mode the server refuses `build_variant` for that conversation. Switching to Auto mode is the person's act, and `auto_start` under a token whose mode is not Auto is refused.

### 2.6 Reads and streaming

A scorecard becomes a pure function of the job plan, the signed job results and the confirmed set. `Lanes.peek(plan)` returns stored results as done and the rest as pending, with no wait. The unsigned `scorecard.json` is deleted, which also closes #105.

```text
GET  /v1/projects                                   list[ProjectSummary]
GET  /v1/projects/{pid}                             briefs, variant sets, waiting items, auto runs
GET  /v1/briefs/{bid}                               brief, proposals, derived status
GET  /v1/projects/{pid}/briefs/{bid}/set            VariantSetView: members, parameters, card etags
GET  /v1/variants/{vid}/scorecard                   ScorecardSnapshot
GET  /v1/variants/{vid}/events                      SSE
GET  /v1/geometry/{brep_sha256}.json                three-cad-viewer shapes, immutable, ETag
POST /v1/members/{ref}/tune                         202 {variant_id}, PersonSession, metered
POST /v1/projects/{pid}/answers                     PersonSession + CSRF
PUT  /v1/conversations/{cid}/mode                   PersonSession
POST /mcp                                           streamable HTTP MCP, AgentToken
```

Each SSE event carries a whole `ScorecardSnapshot` with its etag, not a delta. The handler sends one on connect and one on each job completion, with an in-process notify as the fast path and a 500 ms store poll as the fallback. A reconnect needs no `Last-Event-ID`. The client replaces its copy. `score_variant`'s 20 s wait stays for MCP clients.

### 2.7 Accounts, tenancy and limits

Phase 4 takes the minimum that makes hosting honest:

- Accounts with email magic-link sign-in. Google or GitHub sign-in can come later behind the same `PersonSession`.
- Tenancy by physical partition. `Tenant` extends `Roots` to `~/.cad/accounts/<aid>/{briefs,projects,variants,jobs,geometry}`. One account's operations cannot name another account's path, so isolation holds by construction, per separate-before-serializing-shared-state. No store is shared between tenants, including content-addressed ones, so a cache hit cannot reveal another tenant's geometry.
- Agent tokens. An outside MCP client gets one through MCP authorization (§2.4). Our backend mints a short-lived one per turn.
- `AccountMeter(Meter)` charges container-seconds per account against a daily cap, and every build and check job asks it before its container starts. A capped account gets a refusal before any container starts. The cap is an account limit, not a fourth Auto stop. Auto mode still stops in exactly SPEC's three cases. When the cap refuses a build under an Auto run, the refusal names the account limit, the run makes no further revisions, and the chat says the account limit halted it.
- One replica, enforced. The data root takes an exclusive lease at startup, so a second process on the same root refuses to start. Ballots stop being process state (§2.4). Sessions and Auto state are on disk. Lanes and the semaphore stay in memory and are rebuilt on restart. Shared storage and a job queue wait for measured need.

Out of scope: billing, teams, sharing, and sign-in through a third party such as Google.

## 3. Module map

```text
src/cad/operations/          NEW   registry, Audience, MCP and HTTP adapters
src/cad/accounts/            NEW   Principal, sessions, sign-in, OAuth for /mcp, agent tokens, Tenant, lease, AccountMeter
src/cad/templates/           NEW   declared, rewrite
src/cad/auto/                NEW   model, step, bounds_conflicts, the run log, auto_* operations
src/cad/geometry/            NEW   tessellation as an analysis-image job, content-addressed store
src/cad/web/                 NEW   FastAPI app, SSE, static React build
src/cad/confirmations/       EDIT  FastAPI page, URL elicitation; http.py and the in-memory Desk deleted
src/cad/variant_sets/        EDIT  Member.head, set_by, Tuning log, a read operation
src/cad/checks/lanes.py      EDIT  peek, notify hook
src/cad/scorecard/score.py   EDIT  derive from peek; scorecard.json deleted
src/cad/server/app.py        EDIT  hand-built Tool list deleted, tools come from the registry
web/                         NEW   React app: chat, three-cad-viewer, scorecards, sliders, mode switcher
```

## 4. Sequencing

Each PR ends green on `uv run verify` and is exercised through MCP or the app, as AGENTS.md requires.

0. **ADRs.** An amendment to ADR-0004 records the #47 direction and URL-mode elicitation as the way an outside client opens the page (§2.4). ADR-0010: a template is a `PARAMS` literal, and a tuned variant is ordinary code. ADR-0011: the server holds the Auto run and refines ADR-0002's "only our own agent enforces modes". The operator approved ADR-0010 and ADR-0011 on 2026-11-08. Check: the operator approves the ADR-0004 amendment.
1. **Templates.** `declared`, `rewrite`, `parameters` in the `build_variant` result, `Member.head`, `set_by` and the `Tuning` log. Check: a property test that `declared(rewrite(c, v)) == v`. `cad-call` shows that two values give two ids and a repeated value starts no container.
2. **Operations registry and reads.** Move the tools, add `Lanes.peek`, delete `scorecard.json`. Check: the MCP tool list equals the registry's `AGENT` entries, and generating TypeScript from OpenAPI gives no diff.
3. **Accounts, tenancy, the lease, `/mcp` over HTTP with MCP authorization, and `AccountMeter`.** Check: tenant B gets `UnknownVariant` for tenant A's id. A second process on the same root refuses to start. A capped account is refused before any container starts. Claude Code signs in with `claude mcp login`. The app step reports the SHA over HTTP.
4. **Hosted confirmation.** The FastAPI page, URL elicitation, `Desk` deleted. Check: Playwright signs in and confirms with one click. An agent-token POST, a POST with a stale snapshot, a replay and a session from another account are each refused and write no record. `ask_to_confirm` returns no link in its result. In an interactive Claude Code session the URL dialog opens the page, and under `claude -p` the tool returns `waiting in the web app`. The scripted-person eval still passes through `--opener`.
5. **Geometry.** Tessellation as an analysis-image job and the geometry route. Check: the mesh volume is within 0.5% of the mass check's volume, and a bake-off part renders in three-cad-viewer (screenshot attached).
6. **Web shell.** Viewer, scorecards, SSE. Check: Playwright watches a card go from pending to done without a reload, and no pending row ever has a verdict colour.
7. **Sliders.** `tune`, latest-wins on release, the UI. Check (the first exit): Playwright releases a slider, and the viewer and scorecard update to the new variant without a reload. The release-to-mesh time is printed and not gated. A video is attached.
8. **Auto core.** `step`, `bounds_conflicts`, the run log and the `auto_*` operations. Check: table tests for all pass, oscillation stalling at 3, pending not counting, and a person-set value stopping the run. A scripted driver that keeps calling after `Stopped` is refused with no container started. The property test holds the 300-revision bound. An agent measurement cannot change `step`.
9. **Chat runtime and mode switcher.** Check: a headless scripted-model run through Plan, Design and Auto mode.
10. **Conflict exit eval.** Check (the second exit): on "fits in a 20 mm cube, PLA, at least 50 g" the run stops with `NeedsPerson(conflict, Bounds)` before any build. On a stiffness-versus-mass brief it stops with `conflict, Tradeoff` naming both requirements within 6 revisions. This reuses the brief-set eval driver that phase 2's exit also needs.

Unit 1 and units 2 to 4 are independent and can run in parallel. Unit 8 needs only unit 2.

## 5. Tradeoffs accepted

- We accept a cold build on every slider release. Each is a fresh container, which imports build123d in 2.5 to 3.2 s, and an uncached `build_variant` takes 4.5 to 5.9 s end to end. In exchange we keep one build path and fresh-container isolation, and add no long-lived build process. A value tried before is a store hit.
- We accept a `PARAMS` convention the agent must follow, in exchange for one variant identity and sliders that never call the model.
- We accept that the agent sets slider bounds, in exchange for named sliders. Bounds decide no check.
- We accept that a process driving the person's signed-in browser could press Confirm, in exchange for one click and no extra machinery. The operator accepted this limit in ADR-0004 and in #47.
- We accept that only `Bounds` and `Tradeoff` conflicts are named. Any other conflict shows as `Stalled`, and the report names the requirements whose best never moved.
- We accept one replica, in exchange for not building a distributed queue before anyone needs it.
- We accept the signed tuning log as history. Running git per design waits until someone needs a diff a log cannot give.

## 6. Alternatives considered

- **FastAPI wraps the MCP tools.** Every route becomes a pass-through, and person-only actions such as tuning and confirming become tools an agent can call. The registry hides the same capability behind one list.
- **The agent passes a `parameters` argument, and the variant id hashes a template id and values.** This gives a second identity scheme beside the code hash. The stored code no longer says what was built.
- **Parameters derived from numeric literals by `ast`.** The sliders get names like `const_7` and bounds nobody chose.
- **A warm zygote,** with builds forked from a parent that imported build123d once, at about 17 ms per fork. The operator declined it on 2026-11-08 as MVP cost.
- **A warm pool of single-use containers.** It keeps fresh-container isolation, but each build costs a 2.5 s refill, and every member needs warm containers at 2 GB each.
- **A notification with a sign-in-required link,** by email or in the app's inbox. It works with any client, but it is a scheme of our own. URL-mode elicitation is the standard way a remote MCP server sends a person to a page.
- **OCP.wasm in the browser.** It runs agent Python on the person's machine, outside the sandbox, and the server can no longer vouch for the BREP.
- **A passkey touch per confirmation.** It closes the signed-in-browser gap, but adds WebAuthn, enrolment, recovery and a signed challenge for a gap the operator already accepted. The operator declined it on 2026-11-08.
- **Auto mode's rules in the web app's driver.** A bug there is exactly the unbounded-spend risk, and nothing on the server would stop it.

## 7. Open questions for the operator

1. Should the ADR-0004 amendment adopt URL-mode elicitation as the way an outside client opens the page (§2.4)? The answer is still written only by the page, and a client without URL mode falls back to `waiting in the web app`. This design says yes.
2. Is δ = 0.02 on a margin in [-1, 1] the right threshold for "improved"? SPEC already asks whether three revisions is right.
3. Should `bounds_conflicts` warn on the Plan mode confirmation page? This design says yes.

## 8. Next implementation step

Unit 1 and unit 2 can start at once. Unit 1: add `declared` and `rewrite` with the round-trip property test, and parameterise one bake-off part to exercise it through `cad-call`.
