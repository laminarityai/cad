---
name: protocol-models
description: Model-check the check job queue (src/cad/checks/lanes.py, job_store.py) and the confirmation answer flow (src/cad/confirmations/, records/signed.py) with TLA+. Use when you change how jobs take off, run, are stored or refused, how a worker starts or dies, or how a POST spends a ballot and appends an answer; when `verify` warns that covered code changed; or when a race, a crash, or a second session could break one of these flows.
---

# Protocol models

Unit tests run one interleaving per test. These models run every interleaving, within small bounds, of the threads, server processes, crashes, store errors and agent actions that touch two flows: the check job queue and the confirmation answer flow. A bug in either is expensive and rarely shows up in a test. The queue can run a container twice, leave a check pending forever, or trust a forged result. The answer flow can record an answer twice, lose one it reported as recorded, or record an answer for an item the page never showed.

## Run

```
uv run python .claude/skills/protocol-models/scripts/check_models.py
```

It runs every check in about 35 to 45 s and is the `protocol models` step of `uv run verify`. To run some checks by name, or to print TLC's full trace even when a check passes:

```
uv run python .claude/skills/protocol-models/scripts/check_models.py --trace JobLanesCap
```

After you edit a model, also run the mutants. Each writes a known code regression into a scratch copy of a model, and the run fails unless the model catches it. A mutant that is MISSED means the model no longer guards that property. A STALE mutant means its anchor text changed, so update the anchor.

```
uv run python .claude/skills/protocol-models/scripts/check_models.py --mutants
```

The script needs Java 11 or later. It downloads tla2tools 1.7.4 once to `~/.cache/cad`, checks its sha256, and refuses to run a jar whose hash does not match.

## Why TLA+ and TLC

The properties are about the order in which threads, processes and crashes act on shared state (a lock, a queue, files on disk), and two of them are liveness properties ("eventually stored", "pending ends"). TLC explores every reachable state of a bounded model and checks both kinds, and it returns a shortest counterexample trace. Hypothesis or stateful property tests drive the real code but sample interleavings. They cannot control where a thread is preempted, and they cannot prove that something eventually happens. A Python-level exhaustive explorer would have to be written and trusted. The research overlay is the opposite case. `research/overlay.fill` is a pure function with no concurrency, so tests cover it and a model would add nothing.

## What is verified

### JobLanes.tla: the check job queue

| Property | Kind | The harm it rules out |
| --- | --- | --- |
| `OneContainerPerKey` | invariant | Two containers run the same job in one server process, which doubles cost and races on the result file. |
| `NeverTrustForged` | invariant | A result file someone edited by hand is used as a check result. |
| `InterruptedMeansInterrupted` | invariant | A check is refused as "interrupted 2 times" when it was not interrupted that often. |
| `Converges` | temporal | After crashes, store faults and tampering, a job never ends up stored. The run must end with each job stored, or with fea refused at the attempt cap. |
| `PendingEnds` | temporal | A caller who saw a check pending can poll forever without getting a verdict or a refusal. |
| `TypeOK` and deadlock | invariant | The model reaches a state it did not mean to allow, or it stops with work still to do. |

"A pending row never shows a verdict" is not modeled. The type rules it out (`PendingCheck` has no verdict field), and `tests/scorecard/test_jobs.py` covers the rendering.

| Config | Bounds | Checks |
| --- | --- | --- |
| `JobLanes.cfg` | 1 process, 2 callers, 1 crash, 1 run fault, 1 tamper | invariants |
| `JobLanesCap.cfg` | 1 process, 1 caller, 3 crashes, 1 fault, 1 tamper | invariants and both temporal properties |
| `JobLanesTwoServers.cfg` | 2 processes on one store, 1 caller, 1 crash | invariants (minus the known finding) and both temporal properties |
| `JobLanesTwoServersRefusal.cfg` | the same | the known finding below, which must still be found |

Safety and liveness use separate configs because two callers with liveness takes minutes. One caller is enough for liveness, because a second caller only joins a flight the first one started.

How the model maps to the code:

| Model | Code |
| --- | --- |
| `FeaTakeOff`, `QuickTakeOff` | `Lanes._take_off`: flying lookup, `job_store.read`, `_refusal`, new `Future`, all under `_lock` |
| `Enqueue`, `StartWorker` | `Lanes._enqueue`: `_queue.put`, then `_start_worker` under `_lock` when `_worker is None` |
| `RunQuick`, `WriteQuick`, `SettleQuick`, `ReleaseQuick` | `Lanes._fly` on the caller thread for the quick job |
| `WorkerGet` ... `WorkerRelease` | `Lanes._drain` and `_fly` / `_attempt` on the worker thread: `begin_attempt`, run, `end_attempt` in `finally`, `job_store.write` (skipped on a timeout), settle, `del _flying` |
| `WorkerExit` | `_drain`'s `finally`: clear `_worker`, restart it when the queue is not empty |
| `WaitQuick`, `Land` | `settle`'s `quick.result()` and `_land`: Done, Pending on a timeout, Refused on `SandboxUnavailable` |
| `Crash(p)` | the server process dies: memory is lost, `.attempt` and result files stay |
| `Tamper(j)` | a person edits a stored result file, so its MAC no longer matches |
| `disk`, `attempt` | `job_store` result and `.attempt` files; `Stored(j)` is `job_store.read` with the MAC verified |
| `cut` (ghost) | fea attempts that a crash really interrupted |

The model leaves out the meter, whose refusal, like the cap refusal, is returned and never stored. A run may return a timeout result, which is never stored (see 0f22adb). The phase-3 design said timeouts would be stored; the code deliberately does not store them.

### Answers.tla: the confirmation answer flow

| Property | The harm it rules out |
| --- | --- |
| `OneAnswerPerItem` | Two signed answers for one item, for example from two sessions' pages or a replayed POST. |
| `OneAnswerPerPage` | One page's token records more than one answer. |
| `RecordedIsKept` | The page tells the person "Recorded" but the answer is not in the ledger. |
| `AnswersWhatThePageShowed` | A stored answer is for a revision other than the one the page showed. |

`Answers.cfg` uses 2 server processes, each with its own `Desk`, on one answers directory, with 2 proposal revisions, 2 pages, 3 POSTs, 1 store error and `Attempts = 2`. It finds about 46k states in about 6 s.

| Model | Code |
| --- | --- |
| `Propose` | `propose_requirements` makes a new revision, so the shown item goes stale |
| `Ask(s)` | `ask_to_confirm`, `Desk._open`: keep the open ballot for the same items, else open a new token |
| `Post(g)` | the person's browser POSTs page `g`, possibly again or from a stale page |
| `Find`, `Spend` | `do_POST`: `Desk.find`, then `Desk.spend(token) is not ballot` |
| `CheckLedger`, `CheckPending` | `answer_page`: AlreadyAnswered, then Changed when `pending != ballot.items` |
| `ReadSlots`, `Publish` | `signed.append`: `read_numbered`, `record_for`, `publish` by `os.link`, retry on FileExistsError, Contended |
| `GiveBack` | a store error or Contended makes `do_POST` call `Desk.give_back` |

## Known findings

Each finding is a check that must keep finding its violation. When the code is fixed, the check fails with "wanted exactly X", and the fix is to move that property into the passing config and delete the finding check.

1. `JobLanesTwoServersRefusal` (`InterruptedMeansInterrupted`). Two server processes on one store, for example two Claude Code sessions on `~/.cad`, share `.attempt` files. Server A dies once while fea runs, so `.attempt` is 1. Server B starts the same fea job and `begin_attempt` makes it 2. A restarts, and `score_variant` refuses fea as "interrupted 2 times" while B's healthy run is still going. It clears once B stores its result. It is transient and low severity. The phase-4 one-replica lease would remove it.
2. `AnswersStale` (`StaleWritesNothing`). `answer_page` checks that the pending items still match the page, then appends. If the agent proposes a new revision between the two, the answer is still recorded. It binds to the exact item sha the page showed, so `AnswersWhatThePageShowed` holds, and the newer revision stays pending. Low severity. The trace is 10 states: the POST passes CheckPending, `Propose`, then `Publish` links the answer.

## A failure: real bug or modeling error

When a check fails, read the trace as a story in code terms: which thread or process acted, in which function, and on which state. Then try to reproduce it against the real code, with two `Lanes` instances or two `Desk`s on one temp store and gated runners as in `tests/checks/test_lanes.py`.

- If the code does the same thing, it is a real bug. Stop and report it with the trace, and do not weaken the property to make it pass.
- If the code cannot do what the trace does, the model is wrong. The usual causes are a ghost variable updated at the wrong step, two code steps merged into one atomic action, or a missing fairness condition. Fix the model, then run the mutants.

`/statechart` can draw a trace or a model's actions as a state chart when the trace is long.

## Keeping the models in sync

`check_models.py` reads the block below. It warns when a covered file changed after the sync commit, and it prints a note instead when the commit is not in the clone (CI checks out shallow). The warning does not fail the run. When you see it, read the diff, update the model if the protocol changed, run the checks and the mutants, and only then move `sync` to the new commit. Use `/maintain-formal-verification-skill` for that work.

```coverage
sync: 760c6dc
JobLanes: src/cad/checks/lanes.py src/cad/checks/job_store.py
Answers: src/cad/confirmations/ballot.py src/cad/confirmations/http.py src/cad/confirmations/page.py src/cad/confirmations/answers.py src/cad/records/signed.py
```

## Planned targets, not built yet

These are phase-4 plans. Model them when the code exists.

- **Superseded jobs are dropped.** A background job that has not started for a revision the agent has since replaced is dropped from the queue and never runs. Extend `JobLanes.tla` with revisions and `Lanes.peek`. The property is that no container starts for a superseded revision's job once the replacement has taken off.
- **One replica, enforced by a lease.** When the lease exists, `JobLanesTwoServers` should pass `InterruptedMeansInterrupted`, and the first known finding goes away.
- **Auto mode `step` and its stopping rules** (phase-4 section 2.5). A new model with the agent, the scorecard and the person as actors. Each rule becomes a property: stop when bounds conflict, when all checks pass, when the person is needed, when the agent asks, and at the account limit. Never pass on a pending row. Agent measurements never make a run pass (ADR-0008).

## Not covered

- Real container behaviour, run time and Docker faults beyond "the run fails" or "the process dies".
- The meter. Its refusal takes the same path as the cap refusal, which is modeled.
- The research ledger (ADR-0009). Its rules (the first record wins, a known value is never replaced) live in the pure `research/overlay.fill`, and tests cover it.
- Bounds larger than the configs: more callers, more crashes, more revisions. The bugs these models target show up with two actors and one fault, and larger bounds cost minutes.
