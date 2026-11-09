# The server holds the Auto run

Status: Accepted. The operator approved this ADR on 2026-11-08, with the stop rules below and no progress rule on the server. On 2026-11-09 the operator decided the last two open points: the server keeps the three stop cases it can see itself, and Auto runs only in the web app for now. Nothing is left open. An amendment of 2026-11-09 at the end adds the person's stop.

In Auto mode the agent revises variants against the checks without stopping, until a stop rule ends the run (SPEC, Modes). ADR-0002 made modes agent behavior. The server ships them as guidance, and only our own agent enforces them. That is not enough for Auto mode in phase 4. Auto mode spends compute on every revision. If the rules live in the web app's driver, a bug in the driver can keep a run going after it should have stopped, and nothing on the server would refuse the next build. SPEC names that risk: "Auto mode relies on the agent to stop." This ADR records where the run lives and what stops it. The design is in `docs/design/phase-4.md` §2.5.

## The decision

The server holds each Auto run. The web backend runs the LLM turns and calls the run's tools, `auto_start`, `auto_revise` and `auto_ask`, through the same MCP interface as any client. The server decides when the run stops. Once a run has stopped, the server refuses `build_variant` and `score_variant` under that run before any container starts. A bug in our client can end a run early, but it cannot spend past a stop.

A run stops in these cases:

- **Every requirement passes.** The server decides this from the signed scorecards of the run. A revision counts only once its scorecard has no pending check, so a run never passes on a pending row. Only `Checked` rows count, so an agent measurement (ADR-0008) cannot make a run pass. A pass that rests on research counts, and the stop report says it "passes on researched data" (ADR-0009). An `Unverified` requirement counts as neither pass nor fail, and the stop report lists it. Otherwise a brief with an unchecked requirement could never end its run.
- **The agent needs the person.** The agent calls `auto_ask` with a note when it judges that it is stuck, or that it needs a decision only the person can make, such as which of two conflicting requirements to relax. The note says what the agent tried. The server also stops the run in three cases it can see itself. The operator decided on 2026-11-09 to keep all three:
  - A tool call under the run proposes requirements, because only the person can confirm them. Changing a requirement the person confirmed always means proposing a new one, so this case covers it too.
  - A scorecard row of the latest revision is waiting on the person's confirmation.
  - `auto_start` finds that the confirmed targets conflict before any build. It proves the conflict with interval arithmetic over targets and table rows read by exact key, such as a minimum mass that a material's density and the envelope volume cannot reach. The confirmation page shows the same conflicts as warnings in Plan mode, before the person confirms.
- **The account's usage limit refuses a build.** When the account's meter refuses a build under the run, the run stops, and the chat says that the account limit halted it. The refusal ends the run. The run does not wait for the limit to reset.

The server does not judge progress. It has no margin, no stall rule, no tradeoff detection and no bound on the number of revisions. The agent judges when it is stuck, as Claude Code's model judges when it is done or stuck. The account's usage limit is the backstop for an agent that never stops. It is a daily limit on the account, not a budget for the run.

Run state is an append-only log of signed records at `projects/<pid>/auto/<run>/NNNN.signed`, signed under ADR-0003's scheme. The run's state is derived from the log and is never a stored field, as brief status already is. A replayed `auto_revise` with the same code gives the same variant id, which the log already holds, so it returns the same state and appends nothing.

The person switches modes, in the web app's chat. `set_mode` is an operation that only a person session can call, and no MCP tool exposes it. The agent token that our backend builds for each turn carries the conversation's mode. The server refuses `auto_start` under a token whose conversation is not in Auto mode, and refuses `build_variant` in a conversation in Plan mode.

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

Status: Accepted. The operator directed on 2026-11-09 that the person gets a Stop button for an Auto run, and that leaving Auto mode stops the run through the same path. This amendment records that direction.

A run also stops in a fourth case:

- **The person stops the run.** The person presses Stop in the web app, or switches the conversation out of Auto mode. Either one calls `auto_stop`, an operation that only a person session can call. No MCP tool exposes it, so the agent cannot stop a run in the person's name. `auto_stop` appends a `PersonStopped` record to the run's log, and the run's state becomes `Stopped` with the reason `StoppedByPerson`. On a run that has already stopped, it appends nothing and returns the existing stop. After the stop, the server refuses `auto_revise`, `build_variant` and `score_variant` under the run before any container starts, as for every other stop.

The agent still has its own way to stop, `auto_ask`, and the server's rules are unchanged.

This amendment also makes precise how the agent token carries the mode. The token carries the conversation. At each tool call the server reads that conversation's mode and current Auto run from the account's conversation store. So when the person switches mode or presses Stop during an agent turn, the next tool call in that turn sees the change. A mode or run copied into the token at the start of the turn would stay stale until the turn ends. `build_variant` and `score_variant` take the run from the conversation and have no `auto_run` argument. In Auto mode, both are refused until `auto_start` gives the conversation a run that has not stopped.
