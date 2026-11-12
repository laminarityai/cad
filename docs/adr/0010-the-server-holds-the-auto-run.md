# The server holds the Auto run

Status: Accepted. The operator approved this ADR on 2026-11-08, with the stop rules below and no progress rule on the server. On 2026-11-09 the operator decided the last two open points: the server keeps the three stop cases it can see itself, and Auto runs only in the web app for now. Nothing is left open. Amendments of 2026-11-09 at the end add the person's stop and make every stop leave Auto mode. The amendment of 2026-11-11 removes modes. Auto is the default, and a stop holds the conversation until the person acts.

In Auto mode the agent revises variants against the checks without stopping, until a stop rule ends the run (SPEC, Modes). ADR-0002 made modes agent behavior. The server ships them as guidance, and only our own agent enforces them. That is not enough for Auto mode in phase 4. Auto mode spends compute on every revision. If the rules live in the web app's driver, a bug in the driver can keep a run going after it should have stopped, and nothing on the server would refuse the next build. SPEC names that risk: "Auto mode relies on the agent to stop." This ADR records where the run lives and what stops it. The design is in `docs/design/phase-4.md` §2.5.

## The decision

The server holds each Auto run. The web backend runs the LLM turns and calls the run's tools, `auto_start`, `auto_revise` and `auto_ask`, through the same MCP interface as any client. The server decides when the run stops. Once a run has stopped, the server refuses `build_variant` and `score_variant` under that run before any container starts. A bug in our client can end a run early, but it cannot spend past a stop.

A run stops in these cases:

- **Every requirement passes.** The server decides this from the signed scorecards of the run. A revision counts only once its scorecard has no pending check, so a run never passes on a pending row. Only `Checked` rows count, so an agent measurement (ADR-0008) cannot make a run pass. A pass that rests on research counts, and the stop report says it "passes on researched data" (ADR-0009). A pass of an agent-written check the person approved counts too, and the stop report lists it apart, labelled (ADR-0011). An `Unverified` requirement counts as neither pass nor fail, and the stop report lists it. Otherwise a brief with an unchecked requirement could never end its run.
- **The agent needs the person.** The agent calls `auto_ask` with a note when it judges that it is stuck, or that it needs a decision only the person can make, such as which of two conflicting requirements to relax. The note says what the agent tried. The server also stops the run in three cases it can see itself. The operator decided on 2026-11-09 to keep all three:
  - A tool call under the run proposes requirements, because only the person can confirm them. Changing a requirement the person confirmed always means proposing a new one, so this case covers it too.
  - A scorecard row of the latest revision is waiting on the person's confirmation.
  - `auto_start` finds that the confirmed targets conflict before any build. It proves the conflict with interval arithmetic over targets and table rows read by exact key, such as a minimum mass that a material's density and the envelope volume cannot reach. The confirmation page shows the same conflicts as warnings in Plan mode, before the person confirms.
- **The account's usage limit refuses a build.** When the account's meter refuses a build under the run, the run stops, and the chat says that the account limit halted it. The refusal ends the run. The run does not wait for the limit to reset.

The server does not judge progress. It has no margin, no stall rule, no tradeoff detection and no bound on the number of revisions. The agent judges when it is stuck, as Claude Code's model judges when it is done or stuck. The account's usage limit is the backstop for an agent that never stops. It is a daily limit on the account, not a budget for the run.

Run state is an append-only log of signed records at `projects/<pid>/auto/<run>/NNNN.signed`, signed under ADR-0003's scheme. The run's state is derived from the log and is never a stored field, as brief status already is. A replayed `auto_revise` with the same code gives the same variant id, which the log already holds, so it returns the same state and appends nothing.

The person switches modes, in the web app's chat. `set_mode` is an operation that only a person session can call, and no MCP tool exposes it. The agent token that our backend builds for each turn carries the conversation's mode. The server refuses `auto_start` under a token whose conversation is not in Auto mode, and refuses `build_variant` in a conversation in Plan mode. (Plan mode was removed on 2026-11-11, so that last refusal is gone. See the 2026-11-11 amendment to ADR-0004.)

## How this refines ADR-0002

ADR-0002 still holds. The web app's agent reaches the server only through MCP tools that any client can call, with no private shortcut. What changes is one sentence of its consequences: "Modes and Auto mode's stopping rules are agent behavior." In a web app conversation the server enforces the mode, and for a run it holds it enforces the stop rules. The agent still chooses when it is stuck. The server only refuses to build past a stop.

Modes stay guidance for outside clients. The operator decided on 2026-11-09 that Auto runs only in the web app for now. An outside client's token has `conversation: None`, so it has no mode the server can read, and it cannot start an Auto run. Its spend is still bounded by the account's usage limit, as for any client.

## Considered options

- **Keep Auto mode's rules in the web app's driver.** Rejected. A bug in the driver is exactly the unbounded-spend risk, and nothing on the server would stop it.
- **A stall rule on the server.** A run stopped after three revisions in a row in which no failing requirement's margin beat its best by δ = 0.02. That bounded a run at 300 revisions for each failing requirement. Rejected by the operator on 2026-11-08. It needs a margin for every kind of comparison, a δ to tune, and tradeoff detection, and the agent's own judgment with the usage limit as a backstop does the same job at MVP size.
- **A grader that decides whether the run is making progress.** Rejected by the operator on 2026-11-08 with the stall rule, in favour of the agent's own judgment.
- **A budget for each run.** Not chosen. SPEC says Auto mode has no budget. The account's daily usage limit already bounds spend.

## Consequences

The server proves only conflicts between bounds on one quantity, such as mass or extent. Any other conflict, such as stiffness against mass, reaches the person only when the agent stops and says so. A run where the agent never stops ends at the usage limit, and that can spend a day's compute. SPEC already lists this risk. Watch run lengths and costs from the first Auto run.

The `auto_*` tools join the MCP tool list, because our own agent reaches the server only through MCP. In phase 4 only a web app conversation can hold an Auto run. Giving an outside client a mode needs its own decision.

SPEC's sentence "only our own agent enforces them" changes to say that the server enforces the mode and Auto mode's stop rules in web app conversations, and that modes stay guidance for outside clients.

The phase 4 exit, "Auto mode stops correctly on a brief whose requirements conflict", is tested on two briefs. On a brief whose bounds conflict, the run stops before any build with the proof. On a stiffness-against-mass brief, the agent stops and reports within six revisions, with a note that names both requirements.

## Amendment 2026-11-09: the person can stop a run

Status: Accepted. The operator directed on 2026-11-09 that the person gets a Stop button for an Auto run, and that leaving Auto mode stops the run through the same path. The operator approved this amendment on 2026-11-09.

A run also stops in a fourth case:

- **The person stops the run.** The person presses Stop in the web app, or switches the conversation out of Auto mode. Either one calls `auto_stop`, an operation that only a person session can call. No MCP tool exposes it, so the agent cannot stop a run in the person's name. `auto_stop` appends a `PersonStopped` record to the run's log, and the run's state becomes `Stopped` with the reason `StoppedByPerson`. On a run that has already stopped, it appends nothing and returns the existing stop. After the stop, the server refuses `auto_revise`, `build_variant` and `score_variant` under the run before any container starts, as for every other stop.

The agent still has its own way to stop, `auto_ask`, and the server's rules are unchanged.

The operator decided on 2026-11-09 that the person's Stop also moves the conversation out of Auto mode, to Design. Otherwise the conversation still reads Auto after the Stop, and the agent's next `auto_start` begins a fresh run that the person never asked for. `auto_stop` reads the run's conversation from the run's start record. When the run is that conversation's current run, `auto_stop` switches the conversation to Design through the same path as a switch of mode, and that path stops the run. The agent cannot start Auto again until the person picks Auto. When the person stops an earlier run that is no longer the conversation's current one, only that run stops and the mode is unchanged. The response holds the stopped run and the conversation's mode.

A run belongs to the conversation that started it. Its start record names the conversation, and the conversation names its current run, so the server needs no scan to answer either question. Every `auto_*` tool call must come from that conversation while it is in Auto mode and the run is its current run. Any other call is refused with `RunNotHeld` before anything is recorded or built: a call from another conversation of the same account, a call after the person moved the conversation out of Auto, and a call from a token with no conversation, which is the outside-client shape that cannot run Auto. While a run has not stopped, `auto_start` on its brief from another conversation is refused and the run is not shared.

This amendment also makes precise how the agent token carries the mode. The token carries the conversation. At each tool call the server reads that conversation's mode and current Auto run from the account's conversation store. So when the person switches mode or presses Stop during an agent turn, the next tool call in that turn sees the change. A mode or run copied into the token at the start of the turn would stay stale until the turn ends. `build_variant` and `score_variant` take the run from the conversation and have no `auto_run` argument. In Auto mode, both are refused until `auto_start` gives the conversation a run that has not stopped.

## Amendment 2026-11-09: every stop leaves Auto mode

Status: Accepted. The operator decided on 2026-11-09 that every way an Auto run ends moves its conversation from Auto to Design, so a new Auto run starts only when the person picks Auto.

The previous amendment did this for the person's Stop only. The reviewer of that change saw the same gap live: after the agent's `auto_ask`, the conversation still read Auto, and the agent's next `auto_start` began a fresh run with no step from the person. The same holds for each other ending: every requirement passes, a `NeedsPerson` stop (a conflict, proposed requirements, a requirement that waits on a context part, or the agent's note) and the account's usage limit.

When a run is stopped, for any reason, and it is its conversation's current run, the server switches the conversation to Design. It does this in one place, the function that records every event of a run, so no stop can skip it. A run that was already stopped when the call began gets the same check, so a crash between the stop and the switch is finished by the next call. A stop of a run that is no longer the conversation's current one changes only that run, and the conversation's mode stays, as for the person's Stop. A replayed stop records nothing and changes nothing. A run that stops at its start, on conflicting bounds, leaves its conversation in Design and never holds it in Auto.

The agent learns the result from the refusal of its next call. `auto_start` says that the caller's mode is design, and `auto_revise` and `auto_ask` on the stopped run are refused with `RunNotHeld`. An `auto_ask` on a run that has already stopped used to return the existing stop and is now refused the same way, because the conversation no longer holds the run. In Design mode `build_variant` and `score_variant` follow Design mode and the usual account limit, not the stopped run. A call that was already bound to the run when it stopped is still refused with `RunStopped`.

## Amendment 2026-11-11: Auto is the default and modes are gone

Status: Proposed. The operator decided on 2026-11-11 that Auto is the default, that the mode picker goes away, that any message or page answer from the person reopens Auto after a stop, and that a run revises only against confirmed, checked requirements. This amendment records those decisions. The operator has not yet approved its text.

A conversation has no mode. `set_mode`, its route and the mode on the agent token are removed. The amendments of 2026-11-09 still hold where they speak of a run. Where they speak of Auto mode or Design mode, this amendment replaces them.

### What starts a run

The agent calls `auto_start` when a scored option fails a requirement that the person confirmed and a check decides. The person picks nothing. The server refuses the start in these cases:

- The caller has no web app conversation. Auto still runs only in the web app.
- The brief has no confirmed requirement that a check decides.
- A proposal on the brief waits for the person. So the confirmed set cannot change under a running run.
- A stop holds the conversation (below).
- Another conversation holds a running run on the brief (`RunNotHeld`, unchanged).

A run revises only against `Checked` rows of the confirmed set, and the `AgentChecked` rows of agent-written checks the person approved (ADR-0011). An assumption and a target that waits for Confirm are never in a run's basis.

`auto_start` reads the brief three times, outside the lock: the proposal watermark, then whether a proposal waits, then the confirmed set. The order matters. A proposal that lands after the watermark stops the run at its first gate. If the pending check came first, a proposal between the two reads would sit inside the watermark under a running run. If the confirmed set came first, a proposal confirmed before the pending check would change the decision under the run.

### A stop holds the conversation

The stop cases do not change. A run stops when every requirement passes, when the agent or the server finds that the run needs the person, when the account's usage limit refuses a build, and when the person presses Stop.

Every stop of a conversation's current run holds that conversation. The function that records every event of a run moves the run from the conversation's `auto_run` to its `stopped_run` in one write. A run that was already stopped when the call began gets the same check, so the next call heals a crash between the stop and the write. A run that stops at its start, on conflicting bounds or on a proposal past its watermark, holds the conversation too.

While a stopped run holds the conversation, every tool call there binds that run. The server refuses `build_variant`, `score_variant`, `auto_revise` and `auto_ask` with `RunStopped`, and `auto_start` with `RunRefused`, before any container starts. Before this amendment, the server allowed a build outside the run after a stop. Now nothing builds past a stop until the person acts.

### Only the person lifts the hold

The server clears the stopped run when the chat records the person's message, or a page answer reaching a conversation that waits on it. It clears it before it appends the person's event. So a crash between the two never leaves a person's step that the old stop still holds. A restart that reruns a delivered answer clears nothing, because the person may have pressed Stop after that answer. No tool clears the hold. So the agent cannot build or start a run after a stop until the person has acted.

The person's Stop is unchanged. `auto_stop` is an operation that only a person session can call, and its reply holds the run and the conversation's running and stopped runs.

Outside clients are unchanged. They cannot start a run, and the account's usage limit bounds them.

The protocol model `AutoHold.tla` checks the hold, the start's read order and the crash heal, in `.claude/skills/protocol-models/`.

### What this replaces

It replaces "The person switches modes" in the decision, and the sentence that refuses `auto_start` under a token whose conversation is not in Auto mode. It replaces the amendment "every stop leaves Auto mode", and the sentences of the first 2026-11-09 amendment that move the conversation to Design after the person's Stop. A run that stops at its start no longer leaves its conversation free. `auto_revise` and `auto_ask` on a stopped run that holds the conversation are refused with `RunStopped`, not `RunNotHeld`.

### Considered options

- **A Resume button after a stop.** Rejected by the operator on 2026-11-11. It is a mode picker again, and any message or answer from the person already says they acted.
- **Lift the hold at the start of every turn.** Rejected. A restart reruns the turn of a delivered answer, and the person may have pressed Stop after that answer.
