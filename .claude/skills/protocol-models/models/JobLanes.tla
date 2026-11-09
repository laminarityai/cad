------------------------------ MODULE JobLanes ------------------------------
(***************************************************************************)
(* The check job lanes: src/cad/checks/lanes.py over src/cad/checks/       *)
(* job_store.py. The signed result store is the queue (phase-3 design,     *)
(* central decision 2). Each server process has its own Lanes: the         *)
(* in-flight futures, the background FIFO and its one worker thread. The   *)
(* store under <root>/<vid>/jobs/ is shared by every process and survives  *)
(* a crash. One quick job and one background (fea) job, each with one key. *)
(*                                                                         *)
(* Each action is one step that no other thread can see half done: one     *)
(* `with self._lock:` block, one os.replace, one unlink, one container     *)
(* run, or one Future call. SKILL.md maps every action to its code.        *)
(*                                                                         *)
(* One exception: WorkerBegin is one step, but job_store.begin_attempt     *)
(* reads the .attempt count and then replaces the file, two steps. Two     *)
(* servers that begin the same job at once can both read n and both write *)
(* n + 1, so the real count can be lower than the model's. The model does *)
(* not cover that lost update.                                             *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
    Procs,       \* server processes sharing one store (two Claude Code sessions on ~/.cad)
    Callers,     \* threads calling score_variant in each process
    Cap,         \* job_store.ATTEMPT_CAP
    MaxCrashes,  \* how many times a server may die
    MaxFaults,   \* how many container runs may time out or fail
    MaxTampers,  \* how many times someone without the key may overwrite a result
    Peeks        \* TRUE when callers also read the store with Lanes.peek. It writes only peeked,
                 \* so the configs that check neither peeked nor its finding leave it off.

Jobs == {"quick", "fea"}
Results == {"ok", "timeout", "unavailable", "killed"}
\* ok: a result job_store.write stores. timeout: JobResult.timed_out, which it skips.
\* unavailable: the run raised SandboxUnavailable. killed: the run raised a BaseException
\* (KeyboardInterrupt, SystemExit), which also ends the background worker thread.
FutureStates == {"none", "unset", "ok", "error", "killed"}

VARIABLES
    disk,        \* job_store result file: "none" | "honest" (its MAC verifies) | "forged"
    attempt,     \* job_store .attempt file: its count, 0 when absent
    flying,      \* Lanes._flying: proc -> job -> the state of its Future, "none" when absent
    queue,       \* Lanes._queue: proc -> sequence of queued background jobs
    worker,      \* Lanes._worker: proc -> TRUE when it names a thread
    wpc, wjob, wres,          \* the background worker thread of each process
    cpc, cfea, cquick, cres,  \* each caller thread inside Lanes.settle
    seen,        \* what each caller's last settle returned for fea
    peeked,      \* what each caller's last peek returned for fea
    crashes, faults, tampers,
    cut          \* ghost: fea attempts in a row that a crash ended between begin_attempt and
                 \* end_attempt; an attempt that reaches end_attempt resets it

vars == <<disk, attempt, flying, queue, worker, wpc, wjob, wres,
          cpc, cfea, cquick, cres, seen, peeked, crashes, faults, tampers, cut>>

Threads == Procs \X Callers
Nothing == [kind |-> "none"]

Init ==
    /\ disk = [j \in Jobs |-> "none"]
    /\ attempt = [j \in Jobs |-> 0]
    /\ flying = [p \in Procs |-> [j \in Jobs |-> "none"]]
    /\ queue = [p \in Procs |-> <<>>]
    /\ worker = [p \in Procs |-> FALSE]
    /\ wpc = [p \in Procs |-> "gone"]
    /\ wjob = [p \in Procs |-> "fea"]
    /\ wres = [p \in Procs |-> "ok"]
    /\ cpc = [t \in Threads |-> "idle"]
    /\ cfea = [t \in Threads |-> Nothing]
    /\ cquick = [t \in Threads |-> "none"]
    /\ cres = [t \in Threads |-> "ok"]
    /\ seen = [t \in Threads |-> Nothing]
    /\ peeked = [t \in Threads |-> Nothing]
    /\ crashes = 0 /\ faults = 0 /\ tampers = 0
    /\ cut = 0

\* job_store.read: a result counts only when its MAC verifies for <vid>\0<key>.
Stored(j) == disk[j] = "honest"

RunResults == IF faults < MaxFaults THEN Results ELSE {"ok"}
Spend(r) == faults' = IF r = "ok" THEN faults ELSE faults + 1

FutureOf(r) == CASE r \in {"ok", "timeout"} -> "ok"
                 [] r = "unavailable" -> "error"
                 [] r = "killed" -> "killed"

\* Future.set_result / set_exception on the Future that _flying holds for (p, j). Every
\* thread that took that Future sees it settle. A thread holding an unset Future holds the
\* current one, because a Future leaves _flying only after it settles.
Settle(p, j, r) ==
    /\ flying' = [flying EXCEPT ![p][j] = FutureOf(r)]
    /\ IF j = "fea"
         THEN /\ cfea' = [t \in Threads |->
                    IF t[1] = p /\ cfea[t] = [kind |-> "future", st |-> "unset"]
                      THEN [kind |-> "future", st |-> FutureOf(r)] ELSE cfea[t]]
              /\ UNCHANGED cquick
         ELSE /\ cquick' = [t \in Threads |->
                    IF t[1] = p /\ cquick[t] = "unset" THEN FutureOf(r) ELSE cquick[t]]
              /\ UNCHANGED cfea

-----------------------------------------------------------------------------
(* Lanes.settle on caller thread t = <<p, c>>: take off fea, then quick,   *)
(* then land the fea flight.                                               *)

\* _take_off(fea): the _flying lookup, job_store.read, _refusal and the new Future, all in
\* one `with self._lock:`.
FeaTakeOff(t) ==
    LET p == t[1] IN
    /\ cpc[t] = "idle"
    /\ seen' = [seen EXCEPT ![t] = Nothing]
    /\ IF flying[p]["fea"] # "none" THEN
            /\ cfea' = [cfea EXCEPT ![t] = [kind |-> "future", st |-> flying[p]["fea"]]]
            /\ cpc' = [cpc EXCEPT ![t] = "quick"]
            /\ UNCHANGED flying
       ELSE IF Stored("fea") THEN
            /\ cfea' = [cfea EXCEPT ![t] = [kind |-> "done", value |-> disk["fea"]]]
            /\ cpc' = [cpc EXCEPT ![t] = "quick"]
            /\ UNCHANGED flying
       ELSE IF attempt["fea"] >= Cap THEN
            /\ cfea' = [cfea EXCEPT ![t] = [kind |-> "refused", why |-> "interrupted"]]
            /\ cpc' = [cpc EXCEPT ![t] = "quick"]
            /\ UNCHANGED flying
       ELSE
            /\ flying' = [flying EXCEPT ![p]["fea"] = "unset"]
            /\ cfea' = [cfea EXCEPT ![t] = [kind |-> "future", st |-> "unset"]]
            /\ cpc' = [cpc EXCEPT ![t] = "enqueue"]
    /\ UNCHANGED <<disk, attempt, queue, worker, wpc, wjob, wres, cquick, cres,
                   crashes, faults, tampers, cut>>

\* _enqueue: self._queue.put, outside the lock.
Enqueue(t) ==
    LET p == t[1] IN
    /\ cpc[t] = "enqueue"
    /\ queue' = [queue EXCEPT ![p] = Append(@, "fea")]
    /\ cpc' = [cpc EXCEPT ![t] = "startworker"]
    /\ UNCHANGED <<disk, attempt, flying, worker, wpc, wjob, wres,
                   cfea, cquick, cres, seen, crashes, faults, tampers, cut>>

\* _enqueue: `with self._lock: if self._worker is None: self._start_worker()`.
StartWorker(t) ==
    LET p == t[1] IN
    /\ cpc[t] = "startworker"
    /\ IF ~worker[p]
         THEN /\ worker' = [worker EXCEPT ![p] = TRUE]
              /\ wpc' = [wpc EXCEPT ![p] = "get"]
         ELSE UNCHANGED <<worker, wpc>>
    /\ cpc' = [cpc EXCEPT ![t] = "quick"]
    /\ UNCHANGED <<disk, attempt, flying, queue, wjob, wres,
                   cfea, cquick, cres, seen, crashes, faults, tampers, cut>>

\* _take_off(quick), one `with self._lock:`. A quick job is never refused.
QuickTakeOff(t) ==
    LET p == t[1] IN
    /\ cpc[t] = "quick"
    /\ IF flying[p]["quick"] # "none" THEN
            /\ cquick' = [cquick EXCEPT ![t] = flying[p]["quick"]]
            /\ cpc' = [cpc EXCEPT ![t] = "waitquick"]
            /\ UNCHANGED flying
       ELSE IF Stored("quick") THEN
            /\ cquick' = [cquick EXCEPT ![t] = "none"]
            /\ cpc' = [cpc EXCEPT ![t] = "land"]
            /\ UNCHANGED flying
       ELSE
            /\ flying' = [flying EXCEPT ![p]["quick"] = "unset"]
            /\ cquick' = [cquick EXCEPT ![t] = "unset"]
            /\ cpc' = [cpc EXCEPT ![t] = "runquick"]
    /\ UNCHANGED <<disk, attempt, queue, worker, wpc, wjob, wres, cfea, cres, seen,
                   crashes, faults, tampers, cut>>

\* _fly(quick) -> _attempt -> self._run(job): the quick container, on the caller's thread.
RunQuick(t) ==
    /\ cpc[t] = "runquick"
    /\ \E r \in RunResults :
        /\ cres' = [cres EXCEPT ![t] = r]
        /\ Spend(r)
    /\ cpc' = [cpc EXCEPT ![t] = IF cres'[t] = "ok" THEN "writequick" ELSE "settlequick"]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres,
                   cfea, cquick, seen, crashes, tampers, cut>>

\* _fly: job_store.write, one os.replace. A raised run skips it, and job_store.write skips a
\* timed-out result (RunQuick sends both of those straight to SettleQuick).
WriteQuick(t) ==
    /\ cpc[t] = "writequick"
    /\ disk' = [disk EXCEPT !["quick"] = "honest"]
    /\ cpc' = [cpc EXCEPT ![t] = "settlequick"]
    /\ UNCHANGED <<attempt, flying, queue, worker, wpc, wjob, wres,
                   cfea, cquick, cres, seen, crashes, faults, tampers, cut>>

SettleQuick(t) ==
    /\ cpc[t] = "settlequick"
    /\ Settle(t[1], "quick", cres[t])
    /\ cpc' = [cpc EXCEPT ![t] = "releasequick"]
    /\ UNCHANGED <<disk, attempt, queue, worker, wpc, wjob, wres,
                   cres, seen, crashes, faults, tampers, cut>>

\* _fly finally: `with self._lock: del self._flying[path]`. A failed quick run then raises out
\* of settle, so that call returns no card.
ReleaseQuick(t) ==
    LET p == t[1] IN
    /\ cpc[t] = "releasequick"
    /\ flying' = [flying EXCEPT ![p]["quick"] = "none"]
    /\ cpc' = [cpc EXCEPT ![t] = IF cres[t] \in {"ok", "timeout"} THEN "land" ELSE "idle"]
    /\ cfea' = [cfea EXCEPT ![t] = IF cres[t] \in {"ok", "timeout"} THEN @ ELSE Nothing]
    /\ cquick' = [cquick EXCEPT ![t] = "none"]
    /\ cres' = [cres EXCEPT ![t] = "ok"]
    /\ UNCHANGED <<disk, attempt, queue, worker, wpc, wjob, wres,
                   seen, crashes, faults, tampers, cut>>

\* settle: quick.result() with no timeout, on a Future another thread flies.
WaitQuick(t) ==
    /\ cpc[t] = "waitquick"
    /\ cquick[t] # "unset"
    /\ cpc' = [cpc EXCEPT ![t] = IF cquick[t] = "ok" THEN "land" ELSE "idle"]
    /\ cfea' = [cfea EXCEPT ![t] = IF cquick[t] = "ok" THEN @ ELSE Nothing]
    /\ cquick' = [cquick EXCEPT ![t] = "none"]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres,
                   cres, seen, crashes, faults, tampers, cut>>

\* _land(fea): Done, Pending when the wait runs out first, or Refused on SandboxUnavailable.
\* A BaseException set on the Future raises out of settle, so that call returns no card.
Land(t) ==
    /\ cpc[t] = "land"
    /\ \/ /\ cfea[t].kind # "future"
          /\ seen' = [seen EXCEPT ![t] = cfea[t]]
       \/ /\ cfea[t].kind = "future"
          /\ \/ /\ cfea[t].st = "unset"
                /\ seen' = [seen EXCEPT ![t] = [kind |-> "pending"]]
             \/ /\ cfea[t].st = "ok"
                /\ seen' = [seen EXCEPT ![t] = [kind |-> "done", value |-> "honest"]]
             \/ /\ cfea[t].st = "error"
                /\ seen' = [seen EXCEPT ![t] = [kind |-> "refused", why |-> "unavailable"]]
             \/ /\ cfea[t].st = "killed"
                /\ UNCHANGED seen
    /\ cpc' = [cpc EXCEPT ![t] = "idle"]
    /\ cfea' = [cfea EXCEPT ![t] = Nothing]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres,
                   cquick, cres, crashes, faults, tampers, cut>>

\* Lanes.peek, for the scorecard operation: job_store.read of quick and fea, then
\* interrupted_runs against the cap. No lock, no wait, and no job started.
Peek(t) ==
    /\ Peeks
    /\ cpc[t] = "idle"
    /\ Stored("quick")
    /\ peeked' = [peeked EXCEPT ![t] =
                 IF Stored("fea") THEN [kind |-> "done", value |-> disk["fea"]]
                 ELSE IF attempt["fea"] >= Cap THEN [kind |-> "refused", why |-> "interrupted"]
                 ELSE [kind |-> "pending"]]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres,
                   cpc, cfea, cquick, cres, seen, crashes, faults, tampers, cut>>

-----------------------------------------------------------------------------
(* Lanes._drain, the background worker thread of process p.                *)

\* self._queue.get(), which blocks until a job is queued.
WorkerGet(p) ==
    /\ wpc[p] = "get"
    /\ queue[p] # <<>>
    /\ wjob' = [wjob EXCEPT ![p] = Head(queue[p])]
    /\ queue' = [queue EXCEPT ![p] = Tail(@)]
    /\ wpc' = [wpc EXCEPT ![p] = "begin"]
    /\ UNCHANGED <<disk, attempt, flying, worker, wres, cpc, cfea, cquick, cres, seen,
                   crashes, faults, tampers, cut>>

\* _attempt: job_store.begin_attempt writes interrupted_runs + 1 with one os.replace.
WorkerBegin(p) ==
    /\ wpc[p] = "begin"
    /\ attempt' = [attempt EXCEPT ![wjob[p]] = @ + 1]
    /\ wpc' = [wpc EXCEPT ![p] = "run"]
    /\ UNCHANGED <<disk, flying, queue, worker, wjob, wres, cpc, cfea, cquick, cres,
                   seen, crashes, faults, tampers, cut>>

\* _attempt: self._run(job), the background container.
WorkerRun(p) ==
    /\ wpc[p] = "run"
    /\ \E r \in RunResults :
        /\ wres' = [wres EXCEPT ![p] = r]
        /\ Spend(r)
    /\ wpc' = [wpc EXCEPT ![p] = "end"]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wjob, cpc, cfea, cquick,
                   cres, seen, crashes, tampers, cut>>

\* _attempt finally: job_store.end_attempt unlinks the .attempt file.
WorkerEnd(p) ==
    /\ wpc[p] = "end"
    /\ attempt' = [attempt EXCEPT ![wjob[p]] = 0]
    /\ cut' = IF wjob[p] = "fea" THEN 0 ELSE cut
    /\ wpc' = [wpc EXCEPT ![p] = IF wres[p] = "ok" THEN "write" ELSE "settle"]
    /\ UNCHANGED <<disk, flying, queue, worker, wjob, wres, cpc, cfea, cquick, cres,
                   seen, crashes, faults, tampers>>

\* _fly: job_store.write. A raised run skips it, and job_store.write skips a timed-out one.
WorkerWrite(p) ==
    /\ wpc[p] = "write"
    /\ disk' = [disk EXCEPT ![wjob[p]] = "honest"]
    /\ wpc' = [wpc EXCEPT ![p] = "settle"]
    /\ UNCHANGED <<attempt, flying, queue, worker, wjob, wres, cpc, cfea, cquick,
                   cres, seen, crashes, faults, tampers, cut>>

WorkerSettle(p) ==
    /\ wpc[p] = "settle"
    /\ Settle(p, wjob[p], wres[p])
    /\ wpc' = [wpc EXCEPT ![p] = "release"]
    /\ UNCHANGED <<disk, attempt, queue, worker, wjob, wres, cpc, cres,
                   seen, crashes, faults, tampers, cut>>

\* _fly finally: del self._flying[path]. A BaseException then leaves _drain's loop.
WorkerRelease(p) ==
    /\ wpc[p] = "release"
    /\ flying' = [flying EXCEPT ![p][wjob[p]] = "none"]
    /\ wpc' = [wpc EXCEPT ![p] = IF wres[p] = "killed" THEN "exit" ELSE "get"]
    /\ wres' = [wres EXCEPT ![p] = "ok"]
    /\ UNCHANGED <<disk, attempt, queue, worker, wjob, cpc, cfea, cquick, cres,
                   seen, crashes, faults, tampers, cut>>

\* _drain finally: `with self._lock: self._worker = None; if queued: self._start_worker()`.
WorkerExit(p) ==
    /\ wpc[p] = "exit"
    /\ IF queue[p] # <<>>
         THEN /\ worker' = [worker EXCEPT ![p] = TRUE]
              /\ wpc' = [wpc EXCEPT ![p] = "get"]
         ELSE /\ worker' = [worker EXCEPT ![p] = FALSE]
              /\ wpc' = [wpc EXCEPT ![p] = "gone"]
    /\ UNCHANGED <<disk, attempt, flying, queue, wjob, wres, cpc, cfea, cquick, cres,
                   seen, crashes, faults, tampers, cut>>

-----------------------------------------------------------------------------
(* What the world does.                                                    *)

\* The server process dies. Its futures, queue and worker are gone, and the store keeps every
\* file. Its container is taken to stop with it. In the code it keeps running until it exits:
\* container.remove_orphans removes only exited containers whose owner pid is dead (#148).
Crash(p) ==
    /\ crashes < MaxCrashes
    /\ crashes' = crashes + 1
    /\ cut' = IF wpc[p] \in {"run", "end"} /\ wjob[p] = "fea" THEN cut + 1 ELSE cut
    /\ flying' = [flying EXCEPT ![p] = [j \in Jobs |-> "none"]]
    /\ queue' = [queue EXCEPT ![p] = <<>>]
    /\ worker' = [worker EXCEPT ![p] = FALSE]
    /\ wpc' = [wpc EXCEPT ![p] = "gone"]
    /\ wjob' = [wjob EXCEPT ![p] = "fea"]
    /\ wres' = [wres EXCEPT ![p] = "ok"]
    /\ cpc' = [t \in Threads |-> IF t[1] = p THEN "idle" ELSE cpc[t]]
    /\ cfea' = [t \in Threads |-> IF t[1] = p THEN Nothing ELSE cfea[t]]
    /\ cquick' = [t \in Threads |-> IF t[1] = p THEN "none" ELSE cquick[t]]
    /\ cres' = [t \in Threads |-> IF t[1] = p THEN "ok" ELSE cres[t]]
    /\ seen' = [t \in Threads |-> IF t[1] = p THEN Nothing ELSE seen[t]]
    /\ peeked' = [t \in Threads |-> IF t[1] = p THEN Nothing ELSE peeked[t]]
    /\ UNCHANGED <<disk, attempt, faults, tampers>>

\* Someone without the store key overwrites a result file.
Tamper(j) ==
    /\ tampers < MaxTampers
    /\ tampers' = tampers + 1
    /\ disk' = [disk EXCEPT ![j] = "forged"]
    /\ UNCHANGED <<attempt, flying, queue, worker, wpc, wjob, wres,
                   cpc, cfea, cquick, cres, seen, peeked, crashes, faults, cut>>

\* Only Peek and Crash change peeked.
CallerStep(t) ==
    /\ \/ FeaTakeOff(t) \/ Enqueue(t) \/ StartWorker(t) \/ QuickTakeOff(t) \/ RunQuick(t)
       \/ WriteQuick(t) \/ SettleQuick(t) \/ ReleaseQuick(t) \/ WaitQuick(t) \/ Land(t)
    /\ UNCHANGED peeked

WorkerStep(p) ==
    /\ \/ WorkerGet(p) \/ WorkerBegin(p) \/ WorkerRun(p) \/ WorkerEnd(p) \/ WorkerWrite(p)
       \/ WorkerSettle(p) \/ WorkerRelease(p) \/ WorkerExit(p)
    /\ UNCHANGED peeked

Next ==
    \/ \E t \in Threads : CallerStep(t) \/ Peek(t)
    \/ \E p \in Procs : WorkerStep(p) \/ Crash(p)
    \/ \E j \in Jobs : Tamper(j)

\* Callers keep polling, as the server instructions tell the agent to while a check is pending.
\* Peek has no fairness: a scorecard read is optional, and settle is what moves a job.
Fairness ==
    /\ \A t \in Threads : WF_vars(CallerStep(t))
    /\ \A p \in Procs : WF_vars(WorkerStep(p))

Spec == Init /\ [][Next]_vars /\ Fairness

-----------------------------------------------------------------------------
(* Properties.                                                             *)

Handles ==
    {Nothing, [kind |-> "pending"]}
      \cup [kind : {"future"}, st : FutureStates]
      \cup [kind : {"done"}, value : {"honest", "forged"}]
      \cup [kind : {"refused"}, why : {"interrupted", "unavailable"}]

TypeOK ==
    /\ disk \in [Jobs -> {"none", "honest", "forged"}]
    /\ attempt \in [Jobs -> Nat]
    /\ flying \in [Procs -> [Jobs -> FutureStates]]
    /\ DOMAIN queue = Procs /\ \A p \in Procs : queue[p] \in Seq({"fea"})
    /\ worker \in [Procs -> BOOLEAN]
    /\ wpc \in [Procs -> {"gone", "get", "begin", "run", "end", "write", "settle", "release",
                          "exit"}]
    /\ wjob \in [Procs -> Jobs]
    /\ wres \in [Procs -> Results]
    /\ cpc \in [Threads -> {"idle", "enqueue", "startworker", "quick", "runquick", "writequick",
                            "settlequick", "releasequick", "waitquick", "land"}]
    /\ cfea \in [Threads -> Handles]
    /\ cquick \in [Threads -> FutureStates]
    /\ cres \in [Threads -> Results]
    /\ seen \in [Threads -> Handles]
    /\ peeked \in [Threads -> Handles]
    /\ crashes \in 0..MaxCrashes /\ faults \in 0..MaxFaults /\ tampers \in 0..MaxTampers
    /\ cut \in 0..MaxCrashes

\* No duplicate container: within one process, at most one container runs per job key.
RunningIn(p, j) ==
    Cardinality({t \in Threads : t[1] = p /\ j = "quick" /\ cpc[t] = "runquick"})
      + (IF wpc[p] = "run" /\ wjob[p] = j THEN 1 ELSE 0)
OneContainerPerKey == \A p \in Procs, j \in Jobs : RunningIn(p, j) <= 1

\* A tampered result is never trusted: every Done a caller holds carries the honest result.
NeverTrustForged ==
    \A t \in Threads :
        /\ seen[t].kind = "done" => seen[t].value = "honest"
        /\ peeked[t].kind = "done" => peeked[t].value = "honest"
        /\ cfea[t].kind = "done" => cfea[t].value = "honest"

\* A job is refused as interrupted only after Cap of its attempts in a row really were cut off.
InterruptedMeansInterrupted ==
    \A t \in Threads : seen[t] = [kind |-> "refused", why |-> "interrupted"] => cut >= Cap

\* The same for Lanes.peek: it reports fea refused only after Cap attempts in a row were cut off.
PeekMeansInterrupted ==
    \A t \in Threads : peeked[t] = [kind |-> "refused", why |-> "interrupted"] => cut >= Cap

\* The cap does its job: once Cap fea attempts in a row were cut off by a crash, no fea
\* container runs again, so a job that kills the server is not rerun forever.
CapStopsReruns ==
    \A p \in Procs : wpc[p] = "run" /\ wjob[p] = "fea" => cut < Cap

\* Convergence: whatever crashed, failed or was tampered with, the quick job ends stored with an
\* honest result, and the fea job ends stored or refused by the attempt cap.
Converges ==
    /\ <>[](Stored("quick"))
    /\ <>[](Stored("fea") \/ attempt["fea"] >= Cap)

\* A caller that saw pending, and keeps polling, later sees fea done or refused.
PendingEnds ==
    \A t \in Threads : (seen[t].kind = "pending") ~> (seen[t].kind \in {"done", "refused"})
=============================================================================
