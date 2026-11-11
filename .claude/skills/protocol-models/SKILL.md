---
name: protocol-models
description: Model-check the check job queue (src/cad/checks/lanes.py, job_store.py, including Lanes.peek, the completion listeners and drop_unstarted) the confirmation answer flow (src/cad/confirmations/, operations/confirmation.py, records/signed.py) and how the chat carries on after a page answer (chat/routes.py Chat._deliver, answered, catch_up; chat/answer_driver.py; conversations/store.confirmed) with TLA+. Use when you change how jobs take off, run, are stored or refused, how a worker starts or dies, or who may post the confirmation page, how its snapshot is sealed, or how an answer is appended; when you change what starts a chat turn, how a page answer reaches a conversation, or when Plan ends; when `verify` warns that covered code changed; or when a race, a crash, or a second session could break one of these flows.
---

# Protocol models

Unit tests run one interleaving per test. These models run every interleaving, within small bounds, of the threads, server processes, crashes, store errors and agent actions that touch three flows: the check job queue, the confirmation answer flow, and the chat carrying on after the person answers the page. A bug in any of them is expensive and rarely shows up in a test. The queue can run a container twice, leave a check pending forever, or trust a forged result. The answer flow can record an answer twice, lose one it reported as recorded, record an answer for an item the page never showed, or record one that the agent or another account gave. The carry-on flow can start two turns for one answer, never tell a conversation an answer it waits on, or end Plan after the person picked Plan again.

## Run

```
uv run python .claude/skills/protocol-models/scripts/check_models.py
```

It runs every check in about 30 to 40 s and is the `protocol models` step of `uv run verify`. To run some checks by name, or to print TLC's full trace even when a check passes:

```
uv run python .claude/skills/protocol-models/scripts/check_models.py --trace JobLanesCap
```

After you edit a model, also run the mutants. Each writes a known code regression into a scratch copy of a model, and the run fails unless the model catches it. A mutant that is MISSED means the model no longer guards that property. A STALE mutant means its anchor text changed, so update the anchor.

```
uv run python .claude/skills/protocol-models/scripts/check_models.py --mutants
```

The script needs Java 11 or later. It runs `java -version` first and stops with an install hint when that fails, which is what the macOS `/usr/bin/java` stub does until a JDK is installed. It downloads tla2tools 1.7.4 once to `~/.cache/cad`, tries three times with a pause between tries, checks its sha256, and refuses to run a jar whose hash does not match. CI caches `~/.cache/cad` under a key made from that sha256.

## Why TLA+ and TLC

The properties are about the order in which threads, processes and crashes act on shared state (a lock, a queue, files on disk), and two of them are liveness properties ("eventually stored", "pending ends"). TLC explores every reachable state of a bounded model and checks both kinds, and it returns a shortest counterexample trace. Hypothesis or stateful property tests drive the real code but sample interleavings. They cannot control where a thread is preempted, and they cannot prove that something eventually happens. A Python-level exhaustive explorer would have to be written and trusted. The research overlay is the opposite case. `research/overlay.fill` is a pure function with no concurrency, so tests cover it and a model would add nothing.

## What is verified

### JobLanes.tla: the check job queue

| Property | Kind | The harm it rules out |
| --- | --- | --- |
| `OneContainerPerKey` | invariant | Two containers run the same job in one server process, which doubles cost and races on the result file. |
| `NeverTrustForged` | invariant | A result file someone edited by hand is used as a check result. |
| `InterruptedMeansInterrupted` | invariant | `settle` refuses a check as "interrupted 2 times" when fewer than 2 attempts in a row were cut off by a crash. |
| `CapStopsReruns` | invariant | An fea job that kills the server every time it runs is started again and again. Once `Cap` attempts in a row were cut off, no fea container runs again. |
| `QueuedIsCurrent` | invariant | A background job queued before a newer revision replaced its variant is still queued afterwards, so a container starts for a revision nobody wants. |
| `NotifiedAfterStore` | invariant | A completion listener runs before the result is on disk, so the snapshot it takes misses the result it was told about. |
| `PeekMeansInterrupted` | invariant | The same as `InterruptedMeansInterrupted`, for what `Lanes.peek` reports. It fails today: see known finding 3. |
| `Converges` | temporal | After crashes, store faults and tampering, a job never ends up stored. The run must end with each job stored, or with fea refused at the attempt cap. |
| `PendingEnds` | temporal | A caller who saw a check pending can poll forever without getting a verdict or a refusal. |
| `TypeOK` | invariant | A variable takes a value the model did not mean to allow. It covers every variable. |

TLC's deadlock check is on but proves nothing for this model. A caller can always call `score_variant` again (`FeaTakeOff` is enabled from `idle`), so no state is ever stuck. `Converges` and `PendingEnds` are what show the work finishes.

"A pending row never shows a verdict" is not modeled. The type rules it out (`PendingCheck` has no verdict field), and `tests/scorecard/test_jobs.py` covers the rendering.

| Config | Bounds | Checks |
| --- | --- | --- |
| `JobLanes.cfg` | 1 process, 2 callers, 1 crash, 1 run fault, 1 tamper, 1 replacement | invariants |
| `JobLanesCap.cfg` | 1 process, 1 caller, 3 crashes, 1 fault, 1 tamper, with `peek` | invariants and both temporal properties |
| `JobLanesTwoServers.cfg` | 2 processes on one store, 1 caller, 1 crash, 1 replacement per process | invariants (minus known finding 1) and both temporal properties |
| `JobLanesTwoServersRefusal.cfg` | the same | known finding 1, which must still be found |
| `JobLanesPeek.cfg` | 1 process, 1 caller, 1 crash, with `peek` | known finding 3, which must still be found |

Safety and liveness use separate configs because two callers with liveness takes minutes. One caller is enough for liveness, because a second caller only joins a flight the first one started. `CapStopsReruns` needs at least `Cap` crashes to be tested, so only `JobLanesCap` can catch a broken cap. The constant `Peeks` turns `Peek` on. `Peek` writes only `peeked`, so the configs that check neither `peeked` nor finding 3 leave it off, which keeps the run short.

How the model maps to the code:

| Model | Code |
| --- | --- |
| `FeaTakeOff`, `QuickTakeOff` | `Lanes._take_off`: `job_store.read`, flying lookup, `_interrupted_too_often`, new `Future`, all under `_lock` |
| `FeaTakeOff` (queue branch) | `Lanes._enqueue_locked`, called inside the take-off lock: `_queue.append`, `_wake.notify`, and `_start_worker` when `_worker is None`. The model has no separate enqueue step, because the code has none: a drop cannot fall between take-off and append |
| `Replace(p)` | `Lanes.drop_unstarted`, which `build_into_set` calls when a newer revision takes a variant's slot: under `_lock`, every queued job of the variant leaves `_queue` and `_flying`, and its `Future` gets `Superseded`. A job a worker already took is not in the queue and runs on. `replaces[p]` is ghost: each queued job carries the count at take-off, which `QueuedIsCurrent` compares. It is per process because a drop reaches only its own process's queue |
| `NotifyQuick`, `WorkerNotify` | `Lanes._fly` after `set_result`: the listeners run on the thread that ran the job, outside `_lock`. A listener that raises is logged and swallowed, so the model has no step for it. `told` is ghost: what the listener saw of the store |
| `RunQuick`, `WriteQuick`, `SettleQuick` | `Lanes._fly` on the caller thread for the quick job |
| `WorkerGet` ... `WorkerSettle` | `Lanes._drain` (`_wake.wait` and `popleft` under `_lock`), then `_fly` / `_attempt` on the worker thread: `begin_attempt`, run, `end_attempt` in `finally`, `job_store.write` (skipped on a timeout), then `del _flying` and settle in one lock |
| `WorkerBegin` | `job_store.begin_attempt`, modeled as one step. The code reads the count and then replaces the file, which is two steps (see Not covered) |
| `Peek` | `Lanes.peek` and `_look`: `job_store.read`, then `interrupted_runs >= ATTEMPT_CAP`, with no lock and no `_flying` lookup |
| `WorkerExit` | `_drain`'s `finally`: clear `_worker`, restart it when the queue is not empty |
| `WaitQuick`, `Land` | `settle`'s `quick.result()` and `_land`: Done, Pending on a timeout, Refused on `SandboxUnavailable` or `Superseded` |
| `Crash(p)` | the server process dies: memory is lost, and `.attempt` and result files stay. The model stops its container with it. The code does not: `container.remove_orphans` removes only exited containers whose owner pid is dead (#148) |
| `Tamper(j)` | a person edits a stored result file, so its MAC no longer matches |
| `disk`, `attempt` | `job_store` result and `.attempt` files; `Stored(j)` is `job_store.read` with the MAC verified |
| `cut` (ghost) | fea attempts in a row that a crash really interrupted. An attempt that reaches `end_attempt` resets it, as `end_attempt` resets the file |

The model leaves out the account meter. It refuses inside `container.run`, before `docker run`, by raising `AccountLimitReached`, a `SandboxUnavailable`. So a refusal is a run fault, which the model covers, and is never stored. A run may return a timeout result, which is never stored (see 0f22adb). The phase-3 design said timeouts would be stored; the code deliberately does not store them.

### Answers.tla: the confirmation answer flow

| Property | The harm it rules out |
| --- | --- |
| `OneAnswerPerItem` | Two signed answers for one item, for example from two sessions' pages or a replayed POST. |
| `OneAnswerPerPage` | One snapshot records more than one answer, for example from a double click or a replayed form. |
| `OnlyTenantPersonsAnswer` | A stored answer was given by an agent or by a person of another account. Every stored answer comes from a person session, and its account is the tenant's. |
| `AnsweredByTheOpener` | A form that leaked to another session of the account records an answer. The snapshot is sealed for one session. |
| `RecordedIsKept` | The page tells the person "Recorded" but the answer is not in the ledger. |
| `AnswersWhatThePageShowed` | A stored answer is for a revision other than the one the page showed. |
| `ChangedWritesNothing` | The agent proposed a new revision before the POST reached `answer_page`'s pending check, and the old page's answer is recorded anyway. This is what the Changed guard (`page.py`, `pending(...) != items`) is for. |

A GET mints a snapshot and keeps nothing in memory. So the model has no server process: a POST behaves the same whichever process it reaches, and every process shares one answers directory. Two POSTs of one form both reach `page.answer_page`. Nothing spends a ballot, so `OneRequestPerPage` is gone with `Desk.spend`. The ledger alone stops a replay: `answer_page`'s ledger check, `record_for` and `os.link` each refuse a second answer.

The principals are the tenant's person sessions (`Persons`), a person of another account (`Others`) and the tenant's agents (`Agents`). Any person may post any minted snapshot, its own or a leaked one. An agent has no `Get` or `Post` step, because `verifier.person` refuses its access token. Another account's person never mints a snapshot of this store, because web.py serves it its own tenant. The model lets it post this store's forms anyway, which is more than the code allows, and `Unseal` refuses it. Three guards stop it: web.py serves only the person's own tenant, `answer_page` refuses `person.account != tenant.account`, and the seal binds the account and the session. Any one of them is enough, so the `snapshot-unbound` mutant drops both modeled guards.

`Answers.cfg` uses 2 tenant sessions, 1 session of another account, 1 agent, 2 proposal revisions, 2 snapshots, 3 POSTs, 1 store error and `Attempts = 2`, with a symmetry set over the tenant's sessions. It finds about 83k states in about 5 s. Its deadlock check is real: the `Finished` step is enabled only when every POST is done, so a POST that can take no further step is reported as a deadlock.

| Model | Code |
| --- | --- |
| `Propose` | `propose_requirements` makes a new revision, so every minted snapshot goes stale. `ask_to_confirm` writes nothing, so it has no step |
| `Get(p)` | web.py `show`: `verifier.person`, the person's own tenant, `pending`, then `snapshot.seal` over the account, the session and the items |
| `Post(p, g)` | web.py `record`: a person session POSTs snapshot `g`, possibly again, from a stale page, or one that leaked |
| `Unseal` | `operations/confirmation.answer_page`: the account check, then `snapshot.unseal` with the caller's account and session. The Origin check, `parse_form` and `read_edits` refuse before any write, so the model leaves them out |
| `CheckLedger`, `CheckPending` | `page.answer_page`: AlreadyAnswered, then Changed when `pending != items`. The ghost field `at` keeps the newest revision as `CheckPending` saw it |
| `ReadSlots`, `Publish` | `signed.append`: `read_numbered`, `record_for`, `publish` by `os.link`, retry on FileExistsError, then Contended. A store error or ProjectBusy is a 500 that records nothing, and the person may send the form again |

### CarryOn.tla: the chat carries on after a page answer

After the person answers the confirmation page, the conversation that waits on the answer starts its next turn by itself, and a confirm moves it from Plan to Design. The transcript is the claim. `waiting_on` and `told_through` are derived from the conversation's own transcript, which survives a crash with the ledger and the conversation record. `Channel.running`, the channel cache, pending `on_recorded` calls and scheduled done callbacks live in memory, and a crash loses them. Each `_deliver` runs synchronously on the one event loop, from its `running` check to its append, so the model makes it one step.

| Property | Kind | The harm it rules out |
| --- | --- | --- |
| `OneTurnPerDelivery` | invariant | Two turns act on one delivery, after a double POST, a restart, or an answer that lands while a turn runs. The heal may start a turn again for a delivery whose turn a crash cut before it appended anything. That turn did nothing, so it does not count. |
| `NoAnswerToldTwice` | invariant | A transcript event tells the conversation an answer that an earlier event already told it, so the agent acts on it twice. |
| `NoDeliveryWhileRunning` | action | A delivery `DriverSaid` is appended while a turn runs, which starts a second turn beside the first. |
| `PlanEndsOnlyOnAnEdge` | action | Plan ends in a step that does not move the told cursor over a confirming answer. A level-triggered rule ("the brief is confirmed") would override the person's switch back to Plan. |
| `PendingAskKeepsPlan` | action | A pending `ask_to_confirm` result ends Plan, for example the first ask on a new brief in a project whose older brief was confirmed. |
| `PlanEndsOncePerConfirm` | action | One confirming answer ends Plan twice for a conversation, so a switch back to Plan does not stick. It fails when a crash falls between `store.confirmed` and the append: see known finding 4. |
| `EveryAnswerTold` | temporal | An answer recorded while the conversation waits is never told to it, so the chat stays silent after the person confirmed. |
| `EveryDeliveryRuns` | temporal | A delivery is appended and no turn ever acts on it, for example after a crash between the append and the turn's start. |
| `TypeOK` | invariant | A variable takes a value the model did not mean to allow. |

| Config | Bounds | Checks |
| --- | --- | --- |
| `CarryOn.cfg` | 2 conversations, 2 answers, 2 proposals, 2 asks, 2 messages, 1 crash, 1 switch to Plan, 1 extra `on_recorded` call, symmetry over the conversations | invariants and action properties |
| `CarryOnLive.cfg` | 1 conversation, 2 answers, 2 proposals, 2 asks, 1 message, 1 crash | both temporal properties |
| `CarryOnCut.cfg` | 1 conversation, 1 answer, 1 crash, with `CutBetween` | known finding 4, which must still be found |

Liveness holds under weak fairness on the loop's own steps (the hook, the done callback, the running turn) and on `catch_up`. `catch_up` is fair because the browser's EventSource opens the stream again by itself after a restart. A conversation whose page is closed hears its answer when the person opens it. The person's and the agent's choices (answer, message, propose, ask, switch) are not fair. One conversation is enough for liveness, because each conversation's cursor and channel are its own.

How the model maps to the code:

| Model | Code |
| --- | --- |
| `ledger`, `pending` | the project's signed answers (`read_ledger`), TRUE when an answer confirms a requirements item (`confirms_requirements`), and whether `items.pending` is empty |
| `wait`, `told`, `tail` | `answer_driver.waiting_on` (None is -1), `told_through`, and whether the transcript's last event is a `DriverSaid` with `answered` |
| `mode` | the conversation record's mode. `store.confirmed` moves Plan to Design and leaves Design and Auto alone |
| `Deliver(D)` | `Chat._deliver` for each conversation in `D`: return while `channel.running`, `waiting_on`, `delivery` over the ledger, `store.confirmed` when `ends_plan`, then `_begin` (set `running`, append `DriverSaid(answered=Answered(through=len(ledger)))`, create the turn task) |
| `Hook` | `Chat.answered`, which `confirmations/web.py` `record` calls through `on_recorded` after a recorded answer: `_deliver` on every channel `Channels.open_in` holds |
| `DoneCallback(c)` | the turn task's done callback, which the loop runs some time after `run_turn`'s `finally` cleared `running` |
| `CatchUp(c)` | `Chat.catch_up` on stream open: the restart heal (not running and a `DriverSaid` tail, so start the turn and append nothing), else `_deliver` |
| `Start(c)` | `Chat.start`: refused while running, else `UserSaid` and a turn |
| `TurnActs(c)` | the turn's first append (`AgentSaid`, `ToolCalled` or `TurnFailed`) |
| `AskRead`, `AskItems`, `AskAfter` | `operations/confirmation.ask_to_confirm` after its wait: `answers_recorded` read before the items, the items, and for a result that is not pending the ledger's length read again (see the `answered-count-before-items` mutant) |
| `AskReturn(c)` | `answer_driver.settle` then the `ToolReturned` append, with no await between: move the cursor to `answers_recorded`, and call `store.confirmed` only for a result that is not pending whose new answers confirm |
| `Answer` | `web.py` `record`: one answer to everything pending in the project. Answers.tla shows one recorded POST per answer. `ExtraHook` calls `on_recorded` a second time anyway |
| `Crash` | the process dies: `running`, the channel cache, pending hooks and callbacks go. `CutDeliver` and `CutAsk` die between `store.confirmed` and the append after it |

## Known findings

Each finding is a check that must keep finding its violation. When the code is fixed, the check fails with "wanted exactly X", and the fix is to move that property into the passing config and delete the finding check.

1. `JobLanesTwoServersRefusal` (`InterruptedMeansInterrupted`). Two server processes on one store, for example two Claude Code sessions on `~/.cad`, share `.attempt` files. Server A dies once while fea runs, so `.attempt` is 1. Server B starts the same fea job and `begin_attempt` makes it 2. A restarts, and `score_variant` refuses fea as "interrupted 2 times" while B's healthy run is still going. It clears once B stores its result. It is transient and low severity. The phase-4 one-replica lease would remove it.
2. `AnswersStale` (`StaleWritesNothing`). `answer_page` checks that the pending items still match the page, then appends. If the agent proposes a new revision between the two, the answer is still recorded. It binds to the exact item sha the page showed, so `AnswersWhatThePageShowed` holds, and the newer revision stays pending. Low severity. The trace is 9 states: `Get`, `Post`, the POST passes `Unseal`, `CheckLedger` and `CheckPending`, then `ReadSlots`, `Propose`, and `Publish` links the answer. `StaleWritesNothing` counts only that order (the `stale` ghost requires `at = rev`, so the pending check passed), so this check cannot pass on a stale answer that got past a broken Changed guard. `ChangedWritesNothing` in `Answers.cfg` catches that one.
3. `JobLanesPeek` (`PeekMeansInterrupted`). One server, one crash. The server dies once while fea runs, so `.attempt` is 1. It restarts, `score_variant` starts a healthy rerun, and `begin_attempt` makes `.attempt` 2. While that run is going, `Lanes.peek` (the scorecard operation) reports fea refused as "interrupted 2 times". `settle` does not, because `_take_off` looks in `_flying` first, and `peek` does not. It clears once the run stores its result. Transient and low severity, but it needs only one server, unlike finding 1. Reproduced against the real code: `job_store.begin_attempt` once, then `Lanes.settle` with a gated background runner, then `Lanes.peek` returns `Refused(INTERRUPTED)` while `.attempt` is 2.
4. `CarryOnCut` (`PlanEndsOncePerConfirm`). `_deliver` and `settle` call `store.confirmed` before the append that moves the cursor, so a crash between them leaves the mode in Design and the cursor where it was. The person picks Plan again, the stream reopens, and `catch_up` delivers the same confirm and ends Plan a second time. The trace is 12 states: a message turn proposes and asks (pending), the person confirms while the result returns, the turn ends, the done callback's `_deliver` writes Design and the process dies, the person picks Plan, and `catch_up` delivers. Low severity: it needs a crash in a window with no await and a mode switch before the stream reopens. Writing the mode with the cursor it was written for, so that `confirmed` is a no-op for a cursor already applied, would remove it.

## A failure: real bug or modeling error

When a check fails, read the trace as a story in code terms: which thread or process acted, in which function, and on which state. Then try to reproduce it against the real code, with two `Lanes` instances or two concurrent `answer_page` calls on one temp store and gated runners as in `tests/checks/test_lanes.py`.

- If the code does the same thing, it is a real bug. Stop and report it with the trace, and do not weaken the property to make it pass.
- If the code cannot do what the trace does, the model is wrong. The usual causes are a ghost variable updated at the wrong step, two code steps merged into one atomic action, or a missing fairness condition. Fix the model, then run the mutants.

`/statechart` can draw a trace or a model's actions as a state chart when the trace is long.

## Keeping the models in sync

`check_models.py` reads the block below. It warns when a covered file changed after the sync commit, and it prints a note instead when the commit is not in the clone (CI checks out shallow). The warning does not fail the run. When you see it, read the diff, update the model if the protocol changed, run the checks and the mutants, and only then move `sync` to the new commit. Use `/maintain-formal-verification-skill` for that work.

```coverage
sync: a4c95db
JobLanes: src/cad/checks/lanes.py src/cad/checks/job_store.py src/cad/checks/jobs.py src/cad/sandbox/container.py
Answers: src/cad/confirmations/web.py src/cad/confirmations/snapshot.py src/cad/operations/confirmation.py src/cad/confirmations/page.py src/cad/confirmations/answers.py src/cad/confirmations/items.py src/cad/records/signed.py
CarryOn: src/cad/chat/routes.py src/cad/chat/answer_driver.py src/cad/chat/turn.py src/cad/chat/log.py src/cad/conversations/store.py src/cad/operations/confirmation.py src/cad/confirmations/web.py
```

## Planned targets, not built yet

These are phase-4 plans. Model them when the code exists.

- **One replica, enforced by a lease.** When the lease exists, `JobLanesTwoServers` should pass `InterruptedMeansInterrupted`, and the first known finding goes away.
- **Auto mode `step` and its stopping rules** (phase-4 section 2.5). A new model with the agent, the scorecard and the person as actors. Each rule becomes a property: stop when bounds conflict, when all checks pass, when the person is needed, when the agent asks, and at the account limit. Never pass on a pending row. Agent measurements never make a run pass (ADR-0008).

## Not covered

- Real container behaviour, run time and Docker faults beyond "the run fails" or "the process dies".
- `OneContainerPerKey` holds per process incarnation only. A crashed server's container keeps running, and a restarted server can start a second container for the same key next to it, because `container.remove_orphans` removes only exited containers whose owner pid is dead. Issue #148 tracks it.
- The lost update in `job_store.begin_attempt`. It reads `.attempt` and then replaces it, and the model makes that one step. Two servers that begin the same job at once can both write n + 1, so the real count can be lower than the model's, and the cap can allow more reruns across servers than `Cap`.
- The account meter. Its refusal is a run fault, which is modeled. Its own file lock and day ledger are covered by `tests/accounts/test_meter.py`.
- The research ledger (ADR-0009). Its rules (the first record wins, a known value is never replaced) live in the pure `research/overlay.fill`, and tests cover it.
- Bounds larger than the configs: more callers, more crashes, more revisions. The bugs these models target show up with two actors and one fault, and larger bounds cost minutes.
