# Phase 4 design: the web app

Status: proposed on 2026-11-08. Units 0 to 9 of §4 are built. It was written against commit 2bc3648. Terms follow GLOSSARY.md. Each phase 4 PR is one numbered unit of §4. §7 lists the questions still open for the operator.

The operator made these decisions on 2026-11-08, and this revision records them. The Auto mode ADR, ADR-0010, is approved. The warm per-account zygote is dropped as too costly for an MVP, so builds stay a fresh container per build. SPEC's phase 4 exit no longer has a time target. Accounts and usage limits move from phase 3 to phase 4. A passkey ADR was declined. Hosted confirmation follows the operator's 2026-11-07 direction in #47, recorded as an amendment to ADR-0004 that still needs approval (§4, unit 0).

Later on 2026-11-08 the operator settled the rest at MVP size. Auto mode stops when every requirement passes, when the agent judges it is stuck or needs a decision only the person can make, or when the account's usage cap refuses a build. This works like Claude Code, where the model stops when it thinks it is done or stuck, and the cap is the backstop. The server no longer measures progress, so the margin, δ, the stall and tradeoff rules and the 300-revision bound are removed. `bounds_conflicts` warns on the confirmation page, before the person confirms. The ADR-0004 amendment adopts URL-mode elicitation to open the page, with `waiting in the web app` as the fallback. Two earlier choices of this design stand. A cap refusal ends the Auto run, and tessellation is a background job in the analysis image.

The operator then made two more decisions on 2026-11-08. First, there are no sliders. The person changes a variant by asking in chat, and the agent edits the code and rebuilds. The templates ADR, approved earlier that day as ADR-0010, was withdrawn with sliders, so the Auto mode ADR takes its number. Second, sign-in is Clerk with Google sign-in, in place of the email magic link. Clerk is the OAuth 2.1 authorization server for MCP clients, and our server is only the resource server (§2.4, §2.7).

Phase 4 in SPEC: chat, 3D viewer, scorecards, Auto runs with their stopping rules, and accounts with usage limits. Exit: a change asked for in chat rebuilds the variant and updates its scorecard without a page reload, and an Auto run stops correctly on a brief whose requirements conflict. Phase 4 shipped a mode switcher, which was removed on 2026-11-11 (ADR-0010 amendment).

## What the design starts from

These facts about main shape the design. Each was read in code or measured.

- The server speaks MCP over stdio only (`server/__main__.py`). It has no HTTP API, no accounts, no geometry export tool and no read tool for a variant set or a stored scorecard.
- A variant is opaque agent Python. Its id is a hash of the build image tag, `TRUST_DIGEST` and the code (`variants/entry.py:73`).
- A variant set gives each new code the next slot and refuses a sixth (`variant_sets/store.py`). No build can replace the code in a slot.
- Every build is a fresh `docker run`. Measured on a Mac with Docker Desktop and a warm image: importing build123d in a fresh container takes 2.5 to 3.2 s, and an uncached `build_variant` takes 4.5 to 5.9 s end to end. Phase 4 keeps this path (§5).
- Confirmation is a 127.0.0.1 page with a one-time token in the URL, held in an in-memory `Desk` (ADR-0004). A hosted server cannot open it. A link in a tool result would let the agent confirm itself (#47).
- Claude Code 2.1.287 opens a server's URL for the person through MCP URL-mode elicitation, and the model never sees the URL. This was tested on 2026-11-08 with a one-tool server on mcp 2.3.0 (§2.4).
- The scorecard is written unsigned to `scorecard.json` and never read back. It is also written twice (#105).
- Modes are instruction text. Auto mode has no code.
- Accounts and usage limits were planned for phase 3, but the phase 3 design has no unit for them, and none are built. SPEC now places them in phase 4. `Meter` exists as a seam, wired to `Unmetered` (`checks/jobs.py`).

## Central decisions

1. **One operation registry, two adapters, and an audience on every operation.** Every capability is one typed `Operation` in `cad/operations/`. The MCP tool list and the HTTP routes are both generated from that list. An operation marked `PERSON` only, such as answering the confirmation page or switching modes, has no MCP tool at all. So "the agent cannot confirm" is a property of the registry, not of a check someone must remember. ADR-0002 still holds, because the web app's agent uses the same MCP tools as any outside client.
2. **A person confirms with the Confirm button in the signed-in web app.** This is the operator's direction in #47 (2026-11-07). An amendment to ADR-0004 records it and keeps that ADR's rules: only the page's handler writes the answer, and status is derived from signed records. An outside MCP client signs the person in with MCP authorization, through Clerk, as any remote MCP server does. If the client supports URL-mode elicitation, `ask_to_confirm` asks it to open the page for the person. Otherwise the tool says the proposal is waiting in the web app. On neither path does the agent get a link or a token. The limit stays the one ADR-0003 and ADR-0004 already accept: a process that drives the person's signed-in browser could press the button.
3. **The server holds the Auto run.** The web backend runs the LLM turns. The server decides "all pass" from the signed scorecards of the run, held in a signed per-run log. The agent decides when it is stuck, and says so with `auto_ask`. Once a run is stopped, `build_variant` and `score_variant` under that run are refused before any container starts. A bug in our client cannot spend past a stop.
4. **Phase 4 takes on accounts and usage limits, and Clerk signs people in.** The Confirm button needs a signed-in person, and a hosted app needs tenancy, so the operator moved them from phase 3 to phase 4 on 2026-11-08. Clerk is the authorization server. Our server only verifies Clerk's tokens. Phase 4 runs one replica.

## 1. Usage (caller's view)

### 1a. The person asks for a change in chat

```python
# The person writes "make the wall 4 mm" in chat. The agent edits the code of slot 2 and rebuilds.
build_variant(code=edited, brief_id="b-…", slot=2)
# -> {variant_id, outcome, variant_set: {slot: 2, revision: 3}}
```

```ts
const set = await api.variantSet(projectId, briefId);   // VariantSetView, types generated from Python
const card = api.scorecardStream(variantId);              // SSE, each event a whole ScorecardSnapshot
events.on("variant_built", e => viewer.replace(e.view));  // no reload; the time is recorded, not gated
```

### 1b. The web backend runs Auto mode

```python
run = await mcp.call("auto_start", brief_id=b)  # Continue | Stopped, Bounds conflicts stop here
while isinstance(run, Continue):
    run = await mcp.call("auto_revise", run_id=run.run_id, code=await llm.revise(run.failing))
chat.post(run.report)  # reason, requirements, builds tried, and the agent's note
```

The agent calls `auto_ask(note)` when it judges it is stuck or needs a decision only the person can make. The note says what it tried. The agent can always stop a run, and it can never keep one going past a stop the server decides.

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
- `PERSON`: `answer_page`, `auto_stop`, `list_projects`, `project`, `variant_set`, `view`, `geometry`, `mesh`.
- Both: `list_requirements` (the brief, its proposals and derived status, served at `GET /v1/briefs/{bid}`), `scorecard`, `search_knowledge`, `list_materials`, `server_info`.

A route exists for each `PERSON` or `BOTH` operation, from the `ROUTES` table beside the registry, and for nothing else. A test fails when the two differ.

`server/app.py` stops building `Tool` objects by hand. The existing tools move into the registry in the same PR, and the hand registration is deleted. A test fails if any MCP tool, HTTP route or generated TypeScript type does not come from a registry entry. The adapters parse a `Principal` at the boundary and pass a `Tenant`, so core code never reads module-level roots such as `entry.VARIANTS_ROOT`.

### 2.2 A change asked for in chat

The person asks for a change in chat, and the agent edits the variant's code and calls `build_variant` with the member's `slot`. The new code becomes the slot's next revision, so the set never fills up with edits, and the viewer and scorecard show the slot's latest revision. `auto_revise` builds the same way. Each revision is a signed, append-only record, so earlier revisions stay readable. Code already built is a store hit with no build.

```python
class Revision(Frozen):  # one signed record; the log is one numbered file per revision
    slot: int  # 1..5
    code: str  # kept so a server update can rebuild the slot (variant_sets/model.py)
    code_sha256: str
    built_as: VariantId
    joined_at: datetime


class Member(Frozen):  # derived by grouping the log on slot; never stored
    slot: int
    revisions: tuple[Revision, ...]  # oldest first; the last one is what the set shows
```

### 2.3 Builds

Every build goes through `build_variant`'s existing path: a fresh `docker run` per build, with the limits `container.Job` already sets. There is one build path. On the measured path an uncached build takes 4.5 to 5.9 s. The time from the agent's `build_variant` call to the new mesh is recorded and is not gated.

Tessellation runs as a job in the analysis image (ADR-0005), never in an agent process, so the viewer shows exactly the BREP the checks measured. It runs next to the quick job (closed solid, interference, mass, extents). A new revision plans the full job set. Every row turns pending. The previous number may show as ghost text labelled "before", with no verdict colour, because the type of a pending row has no verdict field. A check job for a revision that a later revision replaced is dropped from the queue if it has not started. If it has started, it finishes and is cached.

### 2.4 Confirmation (amends ADR-0004, resolves #47)

```python
type Principal = PersonSession | AgentToken


class PersonSession(Frozen):
    kind: Literal["person"] = "person"
    account: AccountId  # the Clerk user id
    session_id: str  # the Clerk session id


class AgentToken(Frozen):
    kind: Literal["agent"] = "agent"
    account: AccountId
    token_id: str  # the Clerk OAuth token's id, or our chat agent's turn id
    client_id: str
    conversation: ConversationId | None = None
```

Both kinds of token come from Clerk, so the server tells them apart by Clerk's token type. A person session is a Clerk session token. Clerk's front-end SDK keeps it fresh in the `__session` cookie on our domain. An agent token is a Clerk OAuth access token, sent in an `Authorization: Bearer` header on `/mcp`. Clerk's backend SDK reads the type from the token itself. An OAuth access token is either a JWT whose header `typ` is `at+jwt` or an opaque string that starts with `oat_`, and a session token is neither ([Clerk: verify OAuth tokens](https://clerk.com/docs/guides/configure/auth-strategies/oauth/verify-oauth-tokens), [JWT OAuth access tokens](https://clerk.com/changelog/2026-01-08-jwt-oauth-access-tokens)). The web routes call `authenticate_request` with `accepts_token=["session_token"]`. `/mcp` calls it with `accepts_token=["oauth_token"]`. The Python SDK accepts every type when the list is left out, so each adapter always passes its list, and a test sends each kind of token to the other kind's route and expects 401. Our instance issues OAuth tokens as JWTs, the default for new Clerk applications, so both kinds are JWTs that the server verifies against the instance's JWKS without a network call. Different Starlette route adapters parse them, and `answer_page` is `PERSON` only, so no MCP tool can answer a page.

Our own chat agent needs no token from Clerk. It runs in the server process and reaches the MCP tools through the mcp SDK's in-memory transport, so it gets the same tool list as an outside client (ADR-0002). For each turn the backend builds an `AgentToken` from the person's verified session, with the conversation only. The token carries no mode and no Auto run. At each tool call the server reads the conversation's mode and Auto run from the account's conversation store, so a person's switch of mode or press of Stop takes effect on the agent's next call, even in the middle of a turn. A token with no conversation, such as a Clerk OAuth token from an outside client, has no mode and no Auto run. The token never leaves the process, so there is nothing to leak or revoke.

**How an outside client reaches the page.** The operator wants a person in Claude Code, or any MCP client, to reach the confirmation as with any other remote MCP server. Two parts of the MCP spec do that, and phase 4 uses both.

1. **Sign-in is MCP authorization, with Clerk as the authorization server.** The [authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) makes our server an OAuth 2.1 resource server. It serves Protected Resource Metadata (RFC 9728) at `/.well-known/oauth-protected-resource`, and the metadata names our Clerk instance as the authorization server. Clerk does the rest: dynamic client registration, PKCE, Google sign-in and the consent screen ([Clerk: connect an MCP client](https://clerk.com/docs/guides/ai/mcp/connect-mcp-client), [Clerk OAuth improvements](https://clerk.com/changelog/2025-06-13-oauth-improvements)). Our server verifies the OAuth access token that Clerk issues and builds the `AgentToken` from it. In Claude Code the person runs `/mcp` or `claude mcp login cad` once ([Claude Code MCP docs](https://code.claude.com/docs/en/mcp)). Nobody pastes a token.
2. **The page opens through URL-mode elicitation.** In [URL mode](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation) the server asks the client to open a URL for the person. The client must show the full URL and ask consent before it opens it, and it must open it so that neither the client nor the model can read the page. The answer is out of band. `accept` means only that the person agreed to open the URL. If the client declared `elicitation.url`, `ask_to_confirm` returns an `InputRequiredResult` that asks it to open `https://<app>/projects/<pid>/confirm`. On a 2025-11-25 connection it sends `elicitation/create` with `mode: "url"` instead. The mcp 2.3.0 SDK does both. When the client retries, the tool waits at most 20 s for the signed `PageAnswer`, as today, then returns `waiting`.

The URL carries no token and no answer. It is the page's ordinary address in the app, so it grants nothing without the person's session cookie, and the spec forbids a pre-authenticated URL anyway. The page checks that the session's account is the account of the `AgentToken` that asked, as the spec's phishing rule requires. Status still comes only from the signed `PageAnswer` that the page's handler writes. The server never reads the client's `accept`, `decline` or `cancel` as an answer. Whichever of the three arrives, the tool reports what the signed records say, so a hook that answers the elicitation changes nothing.

This keeps ADR-0004 and #47. ADR-0004 rejected form-mode elicitation because an `Elicitation` hook could answer the form, and that answer was the decision. Here the hook can only accept or decline opening a page. #47 says an outside client gets no link or token, because a link in a tool result lets the agent open it. The tool result still has none. The URL goes to the person through the client's own dialog, and the model never sees it. A process that can drive the person's signed-in browser could still press Confirm, which is the limit ADR-0003 and ADR-0004 already accept.

**Tested on 2026-11-08** with a one-tool server on mcp 2.3.0 and Claude Code 2.1.287, on the 2026-07-28 protocol. Claude Code declared `elicitation: {form, url}`. In an interactive session it showed "MCP server wants to open a URL" with the message, the full URL, and Accept and Decline. Decline reached the server as `action: "decline"`. Under `claude -p` the elicitation came back as `cancel`. The model's transcript did not contain the URL. An `Elicitation` hook did receive the URL. That is harmless, because the URL grants nothing. The [changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) adds URL mode for 2026-07-28 connections in 2.1.281 and for 2025-11-25 connections in 2.1.287. Earlier versions were reported to drop the capability ([#69555](https://github.com/anthropics/claude-code/issues/69555), [#88075](https://github.com/anthropics/claude-code/issues/88075)). An issue reported that the VS Code extension declined URL elicitation ([#35353](https://github.com/anthropics/claude-code/issues/35353), now closed). This design did not test the extension.

**Fallback.** A client that does not declare `elicitation.url`, a headless run, and a person who declines all get the same result: `ask_to_confirm` returns `waiting in the web app`, with no link and no token. The person opens the web app, where every waiting item in the project is on the page. The agent's next call reads the signed answer.

**Onshape.** The Onshape Confirm button from #47 waits for the Onshape extension panel, which SPEC lists as out of scope. Until then, Onshape users confirm in the web app.

The page keeps the `ItemKind` registry, `answers.py` and its sections unchanged. Starlette renders it inside the signed-in app in place of the stdlib server. Its form carries a CSRF token bound to the page snapshot, so "an item added after the page opened records nothing" still holds. `PageAnswer` gains `account` and `session_id`, and the projects key still signs it. The stdlib `ThreadingHTTPServer` page and the in-memory `Desk` are deleted.

Local dev and the eval driver run the same Starlette app on 127.0.0.1, with no Clerk. With `--opener PROGRAM`, the server mints a local person session and hands its sign-in link only to that program, as it hands the page URL today. A local MCP client on stdio gets a local agent token for the same local account. A local verifier takes the Clerk verifier's place at the boundary, and both produce the same `Principal`, so nothing past the boundary knows which one ran. The server uses the local verifier only when it listens on 127.0.0.1 and has no Clerk keys. One page and one answer record serve both.

### 2.5 Auto mode (`cad/auto/`, ADR-0010)

```python
class Standing(Frozen):  # one settled revision, projected from a scorecard
    revision: int
    variant_id: VariantId | None  # None: the build failed
    passes: Mapping[RequirementId, bool | None]
    # None: unknown, unverified, waiting or pending. Only Checked rows give a bool.


type StopReason = AllPass | NeedsPerson | AccountLimit


class NeedsPerson(Frozen):
    kind: Literal["conflict", "proposes_requirements", "source_to_confirm", "agent_asked"]
    requirements: tuple[RequirementId, ...]
    bounds: Bounds | None  # set only for a conflict found before any build
    note: str  # for agent_asked, the agent's report of what it tried


class Bounds(Frozen):  # proved from confirmed targets and tables, before any build
    statement: str  # "min_mass 50 g > density(PLA) 1.24 g/cm³ × envelope 8 cm³ = 9.9 g"
    reads: tuple[Read, ...]  # table rows by exact key, researched rows labelled


class AccountLimit(Frozen):  # the usage cap refused a build under the run
    refused: VariantId | None


class Running(Frozen):
    history: tuple[Standing, ...]


class Stopped(Frozen):
    history: tuple[Standing, ...]
    reason: StopReason
    report: str


type AutoState = Running | Stopped


def bounds_conflicts(reqs: ConfirmedRequirements, tables: Tables) -> tuple[Conflict, ...]: ...
def step(state: Running, standing: Standing) -> AutoState: ...
```

The rules, in order:

1. **Bounds conflict.** `auto_start` runs `bounds_conflicts` before any build. It is interval arithmetic over the kinds that bound one quantity. Mass is bounded by `min_mass`, `max_mass`, and `made_of` density times the `envelope` volume. Extent is bounded by `envelope` and `measure_limit`. It also runs when the person opens the confirmation page, and the page shows each conflict as a warning. So the page warns while the person can still change a target.
2. **All pass.** Every `Checked` requirement passes. `Unverified` requirements are listed in the stop report and count as neither pass nor fail, or Auto could never end on a brief with an unchecked requirement. A pass that rests on research is reported as "passes on researched data" (ADR-0009).
3. **Needs the person.** A tool call under the run that proposes requirements stops the run, because only the person can confirm them. Changing a requirement the person confirmed always means proposing one, so this rule also covers changing what the person stated. A latest scorecard row that is `Waiting` on a confirmation also stops the run. An earlier draft also stopped on a change to a slider value the person had set. That rule went with sliders.
4. **The agent stops.** The agent calls `auto_ask` when it judges it is stuck or needs a decision only the person can make, such as which of two conflicting requirements to relax. The reason is `NeedsPerson(agent_asked)`, and its note says what the agent tried. The server does not judge progress.
5. **The usage cap refuses a build.** When `AccountMeter` refuses a build under the run, the run stops with `AccountLimit` (§2.7).

A revision counts only once its scorecard has no pending check. The server waits for settlement, so a run never passes on a pending row. `standing` reads only `AgainstBrief.requirements` and `Checked` rows, so an agent measurement (ADR-0008) cannot make a run pass, and a test asserts that.

**No length bound on the server.** A run that never passes and that the agent never stops ends when the account's usage cap refuses a build. The cap is the backstop for the SPEC risk that the agent never judges itself stuck. It is a daily account limit, not a per-run budget.

State lives in an append-only signed log at `projects/<pid>/auto/<run>/NNNN.signed`. `AutoState` is a fold over that log, never a stored field, as brief status already is. Replaying `auto_revise` with the same code gives the same variant id, which is already in the log, so it returns the same state without appending.

**Modes** were removed on 2026-11-11. Plan mode went first (ADR-0004 amendment). A brief builds at once, and `build_variant` is no longer refused for want of a confirmation. Then `set_mode` and the mode picker went (ADR-0010, 2026-11-11 amendment). The `AgentToken` carries only the conversation (§2.4). The server reads the conversation's running run and stopped run from the conversation store at each call. The agent calls `auto_start` when a scored option fails a confirmed requirement that a check decides. A run's start record names the conversation that started it, and only that conversation can revise or ask on it. Every stop of a run holds its conversation. The server refuses every build, score and start there until the person's next message or page answer.

### 2.6 Reads and streaming

A scorecard becomes a pure function of the job plan, the signed job results and the confirmed set. `Lanes.peek(plan)` returns stored results as done and the rest as pending, with no wait. The unsigned `scorecard.json` is deleted, which also closes #105.

```text
GET  /v1/projects                                   list[ProjectSummary]
GET  /v1/projects/{pid}                             briefs, variant sets, waiting items, auto runs
GET  /v1/briefs/{bid}                               brief, proposals, derived status
GET  /v1/projects/{pid}/briefs/{bid}/set            VariantSetView: members, revisions, card etags
GET  /v1/variants/{vid}/scorecard                   ScorecardSnapshot
GET  /v1/geometry/{version}/{brep_sha256}.json      three-cad-viewer shapes, immutable, ETag
POST /v1/projects/{pid}/answers                     PersonSession + CSRF
POST /v1/auto/{run}/stop                            PersonSession; the run and the conversation's running and stopped run
GET  /.well-known/oauth-protected-resource          RFC 9728 metadata naming Clerk
POST /mcp                                           streamable HTTP MCP, AgentToken from a Clerk OAuth token
```

The page reads the scorecard route every 1.5 s instead, since a browser holds six connections per host. The events stream planned here was built, never used by the page, and removed ([#232](https://github.com/laminarityai/cad/issues/232)). `score_variant`'s 20 s wait stays for MCP clients.

### 2.7 Accounts, tenancy and limits

Phase 4 takes the minimum that makes hosting honest:

- Accounts are Clerk users, who sign in with Google. The account id is the Clerk user id. Our server stores no password, sign-in link or session. It is only the resource server, and it verifies Clerk's tokens against the instance's JWKS (§2.4).
- Tenancy by physical partition. `Tenant` extends `Roots` to `~/.cad/accounts/<aid>/{briefs,projects,variants,jobs,geometry}`. One account's operations cannot name another account's path, so isolation holds by construction, per separate-before-serializing-shared-state. No store is shared between tenants, including content-addressed ones, so a cache hit cannot reveal another tenant's geometry.
- Agent tokens. An outside MCP client gets a Clerk OAuth access token through MCP authorization, and the server builds the `AgentToken` from it. Our chat agent gets an `AgentToken` built in process for each turn (§2.4).
- `AccountMeter(Meter)` charges container-seconds per account against a daily cap, and every build and check job asks it before its container starts. A capped account gets a refusal before any container starts. When the cap refuses a build under an Auto run, the refusal names the account limit, the run stops with `AccountLimit`, and the chat says the account limit halted it. The cap is a daily account limit, not a per-run budget.
- One replica, enforced. The data root takes an exclusive lease at startup, so a second process on the same root refuses to start. Ballots stop being process state (§2.4). Clerk holds the sessions, and Auto state is on disk. Lanes and the semaphore stay in memory and are rebuilt on restart. Shared storage and a job queue wait for measured need.

Out of scope: billing, teams, sharing, and sign-in methods other than Google.

## 3. Module map

```text
src/cad/operations/          NEW   registry, Audience, MCP and HTTP adapters
src/cad/accounts/            NEW   Clerk token verification, the local verifier, Principal, Tenant, lease, AccountMeter
src/cad/auto/                NEW   model, step, bounds_conflicts, the run log, auto_* operations
src/cad/geometry/            NEW   tessellation as an analysis-image job, content-addressed store
src/cad/web/                 NEW   Starlette app, SSE, static React build
src/cad/confirmations/       EDIT  Starlette page, URL elicitation; http.py and the in-memory Desk deleted
src/cad/variant_sets/        EDIT  revisions in a slot, a read operation
src/cad/checks/lanes.py      EDIT  peek, notify hook
src/cad/scorecard/score.py   EDIT  derive from peek; scorecard.json deleted
src/cad/server/app.py        EDIT  hand-built Tool list deleted, tools come from the registry
web/                         NEW   React app: chat, three-cad-viewer, scorecards, mode switcher, Clerk sign-in
```

## 4. Sequencing

Each PR ends green on `uv run verify` and is exercised through MCP or the app, as AGENTS.md requires.

0. **ADRs.** An amendment to ADR-0004 records the #47 direction and URL-mode elicitation as the way an outside client opens the page (§2.4). ADR-0010: the server holds the Auto run and refines ADR-0002's "only our own agent enforces modes". The operator approved ADR-0010 on 2026-11-08. The templates ADR that first held number 0010 was withdrawn with sliders the same day. Check: the operator approves the ADR-0004 amendment.
1. **Revisions in a slot.** `build_variant` takes a `slot`, and a member holds its signed revisions. Check: `cad-call` builds twice into slot 2, and the set shows the second variant in slot 2 with the first in its history. New code with no `slot` in a full set is still refused, and a repeated revision starts no container.
2. **Operations registry and reads.** Move the tools, add `Lanes.peek`, delete `scorecard.json`. Check: the MCP tool list equals the registry's `AGENT` entries, and generating TypeScript from OpenAPI gives no diff.
3. **Accounts with Clerk, tenancy, the lease, `/mcp` over HTTP, and `AccountMeter`.** Check: Claude Code signs in with `claude mcp login` through Clerk's Google sign-in and consent screen. A Clerk session token on `/mcp` and a Clerk OAuth token on a web route each get 401. The unit also records whether Clerk binds the token's audience to `/mcp` from the `resource` indicator, and the server checks the audience if it does. Tenant B gets `UnknownVariant` for tenant A's id. A second process on the same root refuses to start. A capped account is refused before any container starts. The app step reports the SHA over HTTP.
4. **Hosted confirmation.** The Starlette page, URL elicitation, `Desk` deleted. Check: Playwright signs in and confirms with one click. An agent-token POST, a POST with a stale snapshot, a replay and a session from another account are each refused and write no record. `ask_to_confirm` returns no link in its result. In an interactive Claude Code session the URL dialog opens the page, and under `claude -p` the tool returns `waiting in the web app`. The scripted-person eval still passes through `--opener` with the local verifier.
5. **Geometry.** Tessellation as an analysis-image job and the geometry route. Check: the mesh volume is within 0.5% of the mass check's volume, and a bake-off part renders in three-cad-viewer (screenshot attached).
6. **Web shell.** Viewer, scorecards, SSE. Check: Playwright watches a card go from pending to done without a reload, and no pending row ever has a verdict colour.
7. **Auto core.** `step`, `bounds_conflicts`, the run log and the `auto_*` operations. Check: table tests for all pass, pending not counting toward all pass, proposing requirements stopping the run, `auto_ask` stopping it with the agent's note, and a cap refusal stopping it with `AccountLimit`. A scripted driver that keeps calling after `Stopped` is refused with no container started. An agent measurement cannot change `step`.
8. **Chat runtime and mode switcher.** Check (the first exit): Playwright asks in chat for a change to a variant, and the viewer and scorecard update to the slot's new revision without a reload. The time to the new mesh is printed and not gated. A video is attached. A headless scripted-model run goes through Design and Auto mode.
9. **Conflict exit eval.** Check (the second exit): on "fits in a 20 mm cube, PLA, at least 50 g" the confirmation page warns of the conflict, and the run stops with `NeedsPerson(conflict)` and its `Bounds` before any build. On a stiffness-versus-mass brief the agent stops and reports within 6 builds, counting every build under the run, with a note that names both requirements. This reuses the brief-set eval driver that phase 2's exit also needs.

Unit 1 and units 2 to 4 are independent and can run in parallel. Unit 7 needs only units 1 and 2.

## 5. Tradeoffs accepted

- We accept a cold build on every change. Each is a fresh container, which imports build123d in 2.5 to 3.2 s, and an uncached `build_variant` takes 4.5 to 5.9 s end to end. In exchange we keep one build path and fresh-container isolation, and add no long-lived build process. Code built before is a store hit.
- We accept that every change goes through the model, in exchange for no sliders, no parameter convention and no second way to edit a variant.
- We accept a paid vendor and lock-in to Clerk, in exchange for the least code. We write no authorization server, sign-in page, consent screen or client registration.
- We accept that a revoked Clerk OAuth token in JWT format stays valid until it expires, as Clerk documents, in exchange for verifying it without a network call.
- We accept that a process driving the person's signed-in browser could press Confirm, in exchange for one click and no extra machinery. The operator accepted this limit in ADR-0004 and in #47.
- We accept that the server proves only `Bounds` conflicts. Any other conflict, such as stiffness against mass, reaches the person only when the agent stops and reports it. In exchange, the server has no progress rule to tune. A run where the agent never stops ends at the usage cap.
- We accept one replica, in exchange for not building a distributed queue before anyone needs it.

## 6. Alternatives considered

- **Starlette routes wrap the MCP tools.** Every route becomes a pass-through, and person-only actions such as confirming and switching modes become tools an agent can call. The registry hides the same capability behind one list.
- **Sliders over a `PARAMS` literal.** A template was code with a declared `PARAMS` literal, and the server rewrote the literal for each slider release. The operator approved it as ADR-0010 on 2026-11-08, then withdrew it with sliders the same day. A change asked for in chat needs no parameter convention.
- **A warm zygote,** with builds forked from a parent that imported build123d once, at about 17 ms per fork. The operator declined it on 2026-11-08 as MVP cost.
- **A warm pool of single-use containers.** It keeps fresh-container isolation, but each build costs a 2.5 s refill, and every member needs warm containers at 2 GB each.
- **A notification with a sign-in-required link,** by email or in the app's inbox. It works with any client, but it is a scheme of our own. URL-mode elicitation is the standard way a remote MCP server sends a person to a page.
- **OCP.wasm in the browser.** It runs agent Python on the person's machine, outside the sandbox, and the server can no longer vouch for the BREP.
- **Our own authorization server, with an email magic link.** An earlier draft of this design used it. It needs a sign-in page, client registration, a consent screen and token issuance of our own. The operator chose Clerk on 2026-11-08.
- **Supabase Auth.** It is open source and can act as an OAuth 2.1 server for MCP clients, but its OAuth server is newer than Clerk's. It is the alternative we would move to.
- **Better Auth.** It is a TypeScript library, so it would need a Node service beside our Python server.
- **Firebase Authentication.** It signs people in, but it is not an OAuth server for third-party clients such as Claude Code.
- **A passkey touch per confirmation.** It closes the signed-in-browser gap, but adds WebAuthn, enrolment, recovery and a signed challenge for a gap the operator already accepted. The operator declined it on 2026-11-08.
- **A stall rule on the server.** A run stopped after three revisions in a row in which no failing requirement's margin beat its best by δ = 0.02. It bounded a run at 300 revisions per failing requirement. It also needed a margin for every comparison, a δ to tune, and tradeoff detection. The operator dropped it on 2026-11-08 for the agent's own judgment, with the usage cap as the backstop.
- **Auto mode's rules in the web app's driver.** A bug there is exactly the unbounded-spend risk, and nothing on the server would stop it.

## 7. Open questions for the operator

None.

## 8. Next implementation step

Unit 1 and unit 2 can start at once. Unit 1: add `slot` to `build_variant` and revisions to the set's member records, and build twice into one slot of a bake-off brief through `cad-call`.
