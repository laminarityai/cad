---
name: protocol-models
description: Model-check the check job queue (src/cad/checks/lanes.py, job_store.py, including Lanes.peek, the completion listeners, drop_unstarted and Lanes.close, and how a stopping or restarted server ends its checks: server/stopping.py, container.stop_owned and remove_orphans) the confirmation answer flow (src/cad/confirmations/, operations/confirmation.py, records/signed.py) how the chat carries on after a page answer (chat/routes.py Chat._deliver, answered, catch_up; chat/answer_driver.py) and how a stop holds an Auto run's conversation until the person acts (conversations/store.py record_event, start_run, lift_hold; operations/tenants.bind; auto/gate.py; operations/auto.py auto_start; chat/routes.py Chat._begin) with TLA+. Use when you change how jobs take off, run, are stored or refused, how a worker starts or dies, what a server does to its checks when it stops or starts, or who may post the confirmation page, how its snapshot is sealed, or how an answer is appended; when you change what starts a chat turn, how a page answer reaches a conversation, what stops or holds an Auto run, or what auto_start reads before it opens one; when `verify` warns that covered code changed; or when a race, a crash, or a second session could break one of these flows.
---

# Protocol models

Unit tests run one interleaving per test. These models run every interleaving, within small bounds, of the threads, server processes, crashes, store errors and agent actions that touch four flows: the check job queue, the confirmation answer flow, the chat carrying on after the person answers the page, and the hold a stopped Auto run puts on its conversation. A bug in any of them is expensive and rarely shows up in a test. The queue can run a container twice, leave a check pending forever, or trust a forged result. The answer flow can record an answer twice, lose one it reported as recorded, record an answer for an item the page never showed, or record one that the agent or another account gave. The carry-on flow can start two turns for one answer, or never tell a conversation an answer it waits on. The hold can let the agent build or start a run after a stop before the person acts, or keep a conversation held after the person acted.

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
| `OneContainerPerKey` | invariant | Two containers run the same job in one server process, which doubles cost and races on the result file. It counts the containers that the process's dead incarnations left running. |
| `NeverTrustForged` | invariant | A result file someone edited by hand is used as a check result. |
| `InterruptedMeansInterrupted` | invariant | `settle` refuses a check as "interrupted 2 times" when fewer than 2 attempts in a row were cut off by a crash. A clean stop is not a crash. |
| `CapStopsReruns` | invariant | An fea job that kills the server every time it runs is started again and again. Once `Cap` attempts in a row were cut off, no fea container runs again. |
| `QueuedIsCurrent` | invariant | A background job queued before its variant left its last set is still queued afterwards, so a container starts for a revision nobody wants. |
| `KeptWhileShown` | invariant | A newer revision in one brief drops a queued job whose variant another brief's set still shows, so that brief's caller gets Superseded for a check it waits on. |
| `NotifiedAfterStore` | invariant | A completion listener runs before the result is on disk, so the snapshot it takes misses the result it was told about. |
| `PeekMeansInterrupted` | invariant | The same as `InterruptedMeansInterrupted`, for what `Lanes.peek` reports. |
| `Converges` | temporal | After crashes, clean stops, store faults and tampering, a job never ends up stored. The run must end with each job stored, or with fea refused at the attempt cap. |
| `PendingEnds` | temporal | A caller who saw a check pending can poll forever without getting a verdict or a refusal. |
| `TypeOK` | invariant | A variable takes a value the model did not mean to allow. It covers every variable. |

TLC's deadlock check is on but proves nothing for this model. A caller can always call `score_variant` again (`FeaTakeOff` is enabled from `idle`), so no state is ever stuck. `Converges` and `PendingEnds` are what show the work finishes.

"A pending row never shows a verdict" is not modeled. The type rules it out (`PendingCheck` has no verdict field), and `tests/scorecard/test_jobs.py` covers the rendering.

| Config | Bounds | Checks |
| --- | --- | --- |
| `JobLanes.cfg` | 1 process, 2 callers, 1 crash, 1 run fault, 1 tamper, 2 sets | invariants |
| `JobLanesCap.cfg` | 1 process, 1 caller, 3 crashes, 1 fault, 1 tamper, 1 set, with `peek` | invariants and both temporal properties |
| `JobLanesStop.cfg` | 1 process, 1 caller, 1 clean stop, 2 crashes, 1 fault, 1 set, with `peek` | invariants and both temporal properties |
| `JobLanesTwoServers.cfg` | 2 processes on one store, 1 caller, 1 crash, 2 sets | invariants (minus known finding 1) and both temporal properties |
| `JobLanesTwoServersRefusal.cfg` | 2 processes on one store, 1 caller, 1 crash | known finding 1, which must still be found |

Safety and liveness use separate configs because two callers with liveness takes minutes. One caller is enough for liveness, because a second caller only joins a flight the first one started. `CapStopsReruns` needs at least `Cap` crashes to be tested, so only `JobLanesCap` and `JobLanesStop` can catch a broken cap. A clean stop multiplies the states of every other bound, so only `JobLanesStop` has one. Its two crashes cover a deploy during a check and a stop that a SIGKILL cuts short. `Sets` is how many variant sets show the variant: with 2, one `Replace` keeps the queued job and the second drops it. The constant `Peeks` turns `Peek` on. `Peek` writes only `peeked`, so the configs that do not check `PeekMeansInterrupted` leave it off, which keeps the run short.

How the model maps to the code:

| Model | Code |
| --- | --- |
| `FeaTakeOff`, `QuickTakeOff` | `Lanes._take_off`: `job_store.read`, flying lookup, the `_closed` refusal of a background job, `_interrupted_too_often`, new `Future`, all under `_lock` |
| `FeaTakeOff` (queue branch) | `Lanes._enqueue_locked`, called inside the take-off lock: `_queue.append`, `_wake.notify`, and `_start_worker` when `_worker is None`. The model has no separate enqueue step, because the code has none: a drop cannot fall between take-off and append |
| `Replace(p)` | `variant_sets.store._drop_replaced`, which `build_into_set` calls when a newer revision takes a variant's slot. It calls `Lanes.drop_unstarted`, which under `_lock` reads every set of the account with `account_slots`. When no set still shows the replaced variant, every queued job of the variant leaves `_queue` and `_flying`, and its `Future` gets `Superseded`. The read runs under the lock that queues jobs, so it is one step with the drop. A job a worker already took is not in the queue and runs on. `shown` counts the sets that show the variant. `drops[p]` is ghost: each queued job carries the count at take-off, which `QueuedIsCurrent` compares. It is per process because a drop reaches only its own process's queue |
| `RefuseQueued` | `Lanes._refuse_locked`, which `drop_unstarted` and `close` share: each refused job leaves `_flying`, and its `Future` gets the error |
| `NotifyQuick`, `WorkerNotify` | `Lanes._fly` after `set_result`: the listeners run on the thread that ran the job, outside `_lock`. A listener that raises is logged and swallowed, so the model has no step for it. `told` is ghost: what the listener saw of the store |
| `RunQuick`, `WriteQuick`, `SettleQuick` | `Lanes._fly` on the caller thread for the quick job |
| `WorkerGet` ... `WorkerSettle` | `Lanes._drain` (`_wake.wait` and `popleft` under `_lock`), then `_fly` / `_attempt` on the worker thread: `begin_attempt`, run, `end_attempt` in `finally`, `job_store.write` (skipped on a timeout), then `del _flying` and settle in one lock |
| `WorkerBegin` | `_attempt` under `_lock`: `SandboxUnavailable` when `_closed`, else `job_store.begin_attempt` and `_running = job`. `begin_attempt` is modeled as one step. The code reads the count and then replaces the file, which is two steps (see Not covered) |
| `WorkerEnd` | `_attempt`'s `finally` under `_lock`: while `_running` still names the job, clear it and `end_attempt`. After `close` took the attempt back, it does neither |
| `Peek` | `Lanes.peek` and `_look`, under `_lock`: `job_store.read`, then pending while the job is in `_flying`, else `unfinished_runs >= ATTEMPT_CAP` |
| `WorkerExit` | `_drain`'s `finally`: clear `_worker`, restart it when the queue is not empty |
| `WaitQuick`, `Land` | `settle`'s `quick.result()` and `_land`: Done, Pending on a timeout, Refused on `SandboxUnavailable` or `Superseded` |
| `Close(p)` | `Lanes.close`, the first half of `server/stopping.end_checks`, under `_lock`: set `_closed`, refuse each queued job with `SandboxUnavailable(STOPPED)`, and `job_store.undo_attempt` the job `_running` names. The quick lane stays open |
| `StopOwned(p)` | `container.stop_owned`, the second half of `end_checks`: set the `stopping` event, so `container.run` refuses before and after `docker run`, then `docker rm --force` every container labelled with this pid. A run whose container it removed raises `SandboxUnavailable(STOPPING)`, which spends no fault and is never stored |
| `Exit(p)` | the end of `server/stopping.checks_end_with_the_server`. On SIGTERM its handler runs `end_checks`, restores the default action and raises SIGTERM again. The stdio server runs `end_checks` when the `with` block ends |
| `Crash(p)` | the process dies without `end_checks`: SIGKILL, an out-of-memory kill, or a stop past systemd's timeout. Memory is lost, `.attempt` and result files stay, and its running containers go into `orphans` |
| `Start(p)` | a new server: `hosted.py` and `__main__.py` call `container.remove_orphans` before they serve, which removes every `cad.sandbox` container whose owner pid is dead, running or not |
| `up`, `stopping`, `orphans` | whether a server serves in the process slot; `Lanes._closed` and the `container.stopping` event; the containers dead incarnations left, which `docker ps` would list |
| `Tamper(j)` | a person edits a stored result file, so its MAC no longer matches |
| `disk`, `attempt` | `job_store` result and `.attempt` files; `Stored(j)` is `job_store.read` with the MAC verified |
| `cut` (ghost) | fea attempts in a row that a crash really interrupted. An attempt that reaches `end_attempt` resets it, as `end_attempt` resets the file, and a clean stop does not count |

`StopOwned`, `Exit` and `Start` are weakly fair: a stop that began finishes, and a dead server is started again, by systemd or by the person opening a new session. `Close` is not fair, because a server need never stop.

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

After the person answers the confirmation page, the conversation that waits on the answer starts its next turn by itself. The answer only tells the conversation. `_begin` also lifts a stop's hold, which AutoHold.tla covers. The transcript is the claim. `waiting_on` is derived from the conversation's own transcript, which survives a crash with the ledger. `Channel.running`, the channel cache, pending `on_recorded` calls and scheduled done callbacks live in memory, and a crash loses them. Each `_deliver` runs synchronously on the one event loop, from its `running` check to its append, so the model makes it one step.

| Property | Kind | The harm it rules out |
| --- | --- | --- |
| `OneTurnPerDelivery` | invariant | Two turns act on one delivery, after a double POST, a restart, or an answer that lands while a turn runs. The heal may start a turn again for a delivery whose turn a crash cut before it appended anything. That turn did nothing, so it does not count. |
| `NoAnswerToldTwice` | invariant | A transcript event tells the conversation an answer that an earlier event already told it, so the agent acts on it twice. |
| `NoDeliveryWhileRunning` | action | A delivery `DriverSaid` is appended while a turn runs, which starts a second turn beside the first. |
| `EveryAnswerTold` | temporal | An answer recorded while the conversation waits is never told to it, so the chat stays silent after the person confirmed. |
| `EveryDeliveryRuns` | temporal | A delivery is appended and no turn ever acts on it, for example after a crash between the append and the turn's start. |
| `TypeOK` | invariant | A variable takes a value the model did not mean to allow. |

| Config | Bounds | Checks |
| --- | --- | --- |
| `CarryOn.cfg` | 2 conversations, 2 answers, 2 proposals, 2 asks, 2 messages, 1 crash, 1 extra `on_recorded` call, symmetry over the conversations | invariants and action properties |
| `CarryOnLive.cfg` | 1 conversation, 2 answers, 2 proposals, 2 asks, 1 message, 1 crash | both temporal properties |

Liveness holds under weak fairness on the loop's own steps (the hook, the done callback, the running turn) and on `catch_up`. `catch_up` is fair because the browser's EventSource opens the stream again by itself after a restart. A conversation whose page is closed hears its answer when the person opens it. The person's and the agent's choices (answer, message, propose, ask) are not fair. One conversation is enough for liveness, because each conversation's cursor and channel are its own.

How the model maps to the code:

| Model | Code |
| --- | --- |
| `ledger`, `pending` | the project's signed answers (`read_ledger`), and whether `items.pending` is empty |
| `wait`, `told`, `tail` | `answer_driver.waiting_on` (None is -1), the answers the transcript has told the conversation, and whether the transcript's last event is a `DriverSaid` with `answered` |
| `Deliver(D)` | `Chat._deliver` for each conversation in `D`: return while `channel.running`, `waiting_on`, `delivery` over the ledger, then `_begin` (`lift_hold`, which AutoHold.tla covers, then set `running`, append `DriverSaid(answered=Answered(through=len(ledger)))`, create the turn task) |
| `Hook` | `Chat.answered`, which `confirmations/web.py` `record` calls through `on_recorded` after a recorded answer: `_deliver` on every channel `Channels.open_in` holds |
| `DoneCallback(c)` | the turn task's done callback, which the loop runs some time after `run_turn`'s `finally` cleared `running` |
| `CatchUp(c)` | `Chat.catch_up` on stream open: the restart heal (not running and a `DriverSaid` tail, so start the turn and append nothing), else `_deliver`. Before `_deliver`, a turn a restart cut off after it started gets `TurnFailed` and `TurnEnded`. Neither is a delivery, and the tail was not one, so `tail`, `told` and `wait` stay as they were and the model has no step for it |
| `Start(c)` | `Chat.start`: refused while running, else `UserSaid` and a turn |
| `TurnActs(c)` | the turn's first append (`AgentSaid`, `ToolCalled` or `TurnFailed`) |
| `AskRead`, `AskItems`, `AskAfter` | `operations/confirmation.ask_to_confirm` after its wait: `answers_recorded` read before the items, the items, and for a result that is not pending the ledger's length read again (see the `answered-count-before-items` mutant) |
| `AskReturn(c)` | the `ToolReturned` append: the told cursor moves to `answers_recorded`, and a pending result starts the wait |
| `Answer` | `web.py` `record`: one answer to everything pending in the project. Answers.tla shows one recorded POST per answer. `ExtraHook` calls `on_recorded` a second time anyway |
| `Crash` | the process dies: `running`, the channel cache, pending hooks and callbacks go |

### AutoHold.tla: a stop holds the conversation

Every stop of an Auto run holds its web app conversation (ADR-0010). `record_event` moves the run from `auto_run` to `stopped_run` in the write that records the stop. `bind` gives every tool call the running run or else the stopped run, so the gate refuses each build and score after a stop, and `start_run` refuses a new run. Only `Chat._begin`, for the person's message or a delivered page answer, calls `lift_hold`. The model has one account, one project and one brief. The run logs and the conversation records are on disk and every write takes `store._LOCK`, so each write is one step. A crash can fall between a stop and its conversation write, and the next call in that conversation writes the hold. `auto_start` reads the brief three times outside the lock, and any caller may propose between the reads.

| Property | Kind | The harm it rules out |
| --- | --- | --- |
| `NoBuildPastAStop` | invariant | A build or score passes the gate in a conversation whose run stopped, before the person acted. |
| `NoRunWithoutAPersonStep` | invariant | The agent starts a run after a stop, before the person acted. |
| `OnlyAPersonStepReopens` | action | Something other than `_begin` clears `stopped_run`, such as a tool call or the restart heal rerunning a delivery that came before a Stop. |
| `StopSticks` | action | A stopped run runs again. |
| `OneRunningRunPerConversation` | invariant | A running run is not its conversation's `auto_run`, so a conversation holds two runs or loses track of one. |
| `OnlyTheOwnerDrives` | invariant | A conversation binds a run that another conversation started. |
| `NoBuildUnderAPendingProposal` | invariant | A build passes a run's gate while a proposal on its brief waits for the person. |
| `BuiltUnderItsDecision` | invariant | A build under a run is judged against a confirmed set the run did not start from. |
| `ActedLiftsTheHold` | invariant | A turn that serves the person's act runs held by a stop from before the act. |
| `HealedByTheNextCall` | invariant | A stop that a crash cut before its conversation write is still unwritten after the conversation's next call. |
| `TypeOK` | invariant | A variable takes a value the model did not mean to allow. |

| Config | Bounds | Checks |
| --- | --- | --- |
| `AutoHold.cfg` | 2 conversations, 2 runs, 2 proposals, 2 person acts per conversation, 1 crash, symmetry over the conversations | every property. The hold makes no liveness claim |

The order of `auto_start`'s reads matters. It reads the watermark, then checks for a pending proposal, then reads the confirmed set. A proposal that lands after the watermark stops the run at its first gate. If the pending check came first, a proposal between the two reads would sit inside the watermark and never stop the run (`pending-before-watermark`). If the confirmed set came before the pending check, a proposal confirmed between them would change the decision under the run (`confirmed-before-pending`). `tests/auto/test_run.py` lands a proposal after each of the first two reads of the real code.

`_begin` lifts the hold before it appends the person's event, and the restart heal lifts nothing. With the append first, a crash between the two leaves a delivery whose rerun turn the old stop still holds (`append-before-lift`). A heal that lifted would clear a Stop the person pressed after the delivery (`heal-lifts-the-hold`).

| Model | Code |
| --- | --- |
| `props`, `Pending`, `Decision` | the brief's proposals, `BriefState.latest` with status PROPOSED, and `BriefState.confirmed`. A newer proposal supersedes an older one, so only the latest is answered |
| `auto`, `stopped`, `Bound(c)` | `Conversation.auto_run` and `stopped_run`, and `tenants.bind` (`auto_run or stopped_run`) |
| `Record(r)` | `store.record_event` for an event that stops the run: `append_event` (nothing on a stopped run), then `_held_by` when the run is the conversation's `auto_run`, also for a run already stopped |
| `Stop(r)` | `auto_stop`, the person's Stop on any run, any time |
| `StopCrash(r)` | any stop whose process dies before `record_event` writes the conversation |
| `Begin(c)`, `Run(c)` | `Chat._begin` while no turn runs: `lift_hold` (the stale current run, then `stopped_run`), then `channel.append`, then `_run`. `First` and `Second` name the two writes so a mutant can swap them |
| `Heal(c)` | `Chat.catch_up`'s restart heal: a delivery tail and no turn, so the turn runs again with no lift |
| `Build(c)` | `build_variant`, `score_variant` or `auto_revise`: `bind`, then `gate` and `record_proposals`, which stops the run with Proposed when a proposal came after the watermark. Only the conversation's own agent starts a run in it and a person act waits for the turn to end, so `bind`'s unlocked read and the gate are one step |
| `Ask(c)` | `auto_ask` on the bound run. It also stands for the account cap, which `stops_at_the_limit` records through `record_event` in the same conversation |
| `StartCall`, `Read`, `Open` | `auto_start`: the reads in `ReadOrder`, then `start_run` under the lock with `open_under_lock`, which returns the brief's running run to its conversation, refuses it to another (RunNotHeld), or creates the next run. A new run stops at once when a proposal came after its watermark, or when its bounds conflict |
| `Propose`, `Answer` | `propose_requirements` from any caller, and the person's page answer |
| `acted`, `holdAt`, `on`, `untouched` | ghosts: the person acted since the last stop, the act count at that stop, the act a turn serves, and a crash-cut stop no call has healed |

`record_proposals` reads the run and the proposals and then records, and the model makes that one step. A proposal that lands between the read and the record is caught at the next gate. The stop rules themselves (all pass, conflict, the agent asks) are the pure fold in `auto/step.py`, which `tests/auto/test_step.py` covers. The model only needs to know that a record stops a run. `Tried`, which every build under a run appends through `record_event` when its container returns, changes no hold and stops no run, so the model leaves it out. The person's `PersonStopped` also records whether a build under the run was still running, read from `auto/building.py` in memory under the same lock. That flag changes only the report, so `Stop(r)` stays one step.

## Known findings

Each finding is a check that must keep finding its violation. When the code is fixed, the check fails with "wanted exactly X", and the fix is to move that property into the passing config and delete the finding check.

1. `JobLanesTwoServersRefusal` (`InterruptedMeansInterrupted`). Two server processes on one store, for example two Claude Code sessions on `~/.cad`, share `.attempt` files. Server A dies once while fea runs, so `.attempt` is 1. Server B starts the same fea job and `begin_attempt` makes it 2. A restarts, and `score_variant` refuses fea as "interrupted 2 times" while B's healthy run is still going. It clears once B stores its result. It is transient and low severity. The phase-4 one-replica lease would remove it.
2. `AnswersStale` (`StaleWritesNothing`). `answer_page` checks that the pending items still match the page, then appends. If the agent proposes a new revision between the two, the answer is still recorded. It binds to the exact item sha the page showed, so `AnswersWhatThePageShowed` holds, and the newer revision stays pending. Low severity. The trace is 9 states: `Get`, `Post`, the POST passes `Unseal`, `CheckLedger` and `CheckPending`, then `ReadSlots`, `Propose`, and `Publish` links the answer. `StaleWritesNothing` counts only that order (the `stale` ghost requires `at = rev`, so the pending check passed), so this check cannot pass on a stale answer that got past a broken Changed guard. `ChangedWritesNothing` in `Answers.cfg` catches that one.

## A failure: real bug or modeling error

When a check fails, read the trace as a story in code terms: which thread or process acted, in which function, and on which state. Then try to reproduce it against the real code, with two `Lanes` instances or two concurrent `answer_page` calls on one temp store and gated runners as in `tests/checks/test_lanes.py`.

- If the code does the same thing, it is a real bug. Stop and report it with the trace, and do not weaken the property to make it pass.
- If the code cannot do what the trace does, the model is wrong. The usual causes are a ghost variable updated at the wrong step, two code steps merged into one atomic action, or a missing fairness condition. Fix the model, then run the mutants.

`/statechart` can draw a trace or a model's actions as a state chart when the trace is long.

## Keeping the models in sync

`check_models.py` reads the block below. It warns when a covered file changed after the sync commit, and it prints a note instead when the commit is not in the clone (CI checks out shallow). The warning does not fail the run. When you see it, read the diff, update the model if the protocol changed, run the checks and the mutants, and only then move the sync commit. `sync:` is the commit for every model line that names none. A line written `Model@<commit>:` has its own, so you can move one model after you audit only that one. Use `/maintain-formal-verification-skill` for that work.

```coverage
sync: 21a7efb
JobLanes: src/cad/checks/lanes.py src/cad/checks/job_store.py src/cad/checks/jobs.py src/cad/sandbox/container.py src/cad/server/stopping.py src/cad/variant_sets/store.py
Answers: src/cad/confirmations/web.py src/cad/confirmations/snapshot.py src/cad/operations/confirmation.py src/cad/confirmations/page.py src/cad/confirmations/answers.py src/cad/confirmations/items.py src/cad/records/signed.py
CarryOn: src/cad/chat/routes.py src/cad/chat/answer_driver.py src/cad/chat/turn.py src/cad/chat/log.py src/cad/conversations/store.py src/cad/operations/confirmation.py src/cad/confirmations/web.py
AutoHold@72b073d: src/cad/auto/gate.py src/cad/auto/log.py src/cad/operations/auto.py src/cad/conversations/store.py src/cad/chat/routes.py src/cad/operations/tenants.py src/cad/operations/variants.py src/cad/auto/building.py
```

## Planned targets, not built yet

These are phase-4 plans. Model them when the code exists.

- **One replica, enforced by a lease.** When the lease exists, `JobLanesTwoServers` should pass `InterruptedMeansInterrupted`, and the first known finding goes away.

## Not covered

- Real container behaviour, run time and Docker faults beyond "the run fails" or "the process dies". A dockerd restart or a `docker kill` from outside ends a run the way a crashing check does, so its result is stored as the check's own.
- A container that `container.run` starts after `stop_owned` listed this pid's containers. The model makes `StopOwned` one step. In the code, a run that passed its `stopping` check before the event was set can start `docker run` after the listing. The container then runs on as an orphan until the next server's `remove_orphans`.
- Owner pids. `remove_orphans` treats a container as live while any process has its owner pid, so a reused pid keeps an orphan until that process ends. It also assumes every server that shares the Docker daemon shares one pid namespace.
- The lost update in `job_store.begin_attempt`. It reads `.attempt` and then replaces it, and the model makes that one step. Two servers that begin the same job at once can both write n + 1, so the real count can be lower than the model's, and the cap can allow more reruns across servers than `Cap`.
- The account meter. Its refusal is a run fault, which is modeled. Its own file lock and day ledger are covered by `tests/accounts/test_meter.py`.
- The Auto stop rules. `auto/step.py` folds a run's events with no concurrency, so `tests/auto/test_step.py` covers it. AutoHold.tla covers what a stop does to the conversation.
- The research ledger (ADR-0009). Its rules (the first record wins, a known value is never replaced) live in the pure `research/overlay.fill`, and tests cover it.
- Bounds larger than the configs: more callers, more crashes, more revisions. The bugs these models target show up with two actors and one fault, and larger bounds cost minutes.
