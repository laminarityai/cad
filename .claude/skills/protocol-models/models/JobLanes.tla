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
(* A job joins the queue in the same lock that puts it in _flying, so a   *)
(* Lanes.drop_unstarted never sees a flying job that is not yet queued.    *)
(* Listeners hear of a stored job after its Future is settled, outside the *)
(* lock (Lanes.subscribe).                                                 *)
(*                                                                         *)
(* A server that stops ends its own checks first (src/cad/server/          *)
(* stopping.py): Close, StopOwned, then Exit. A server that dies without   *)
(* that leaves its containers running as orphans, and the next server to   *)
(* start removes them before it serves a call (Start).                     *)
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
    MaxStops,    \* how many times a server stops cleanly, as a deploy's SIGTERM stops it
    Sets,        \* how many variant sets show the variant in a slot. Each Replace takes it out of
                 \* one, and the last one out calls drop_unstarted. 0 turns Replace off.
    Peeks        \* TRUE when callers also read the store with Lanes.peek. It writes only peeked,
                 \* so the configs that check neither peeked nor its finding leave it off.

Jobs == {"quick", "fea"}
Results == {"ok", "timeout", "unavailable", "killed"}
\* ok: a result job_store.write stores. timeout: JobResult.timed_out, which it skips.
\* unavailable: the run raised SandboxUnavailable. killed: the run raised a BaseException
\* (KeyboardInterrupt, SystemExit), which also ends the background worker thread.
FutureStates == {"none", "unset", "ok", "error", "killed", "dropped"}
\* dropped: drop_unstarted set Superseded on a Future whose job no worker had taken.

VARIABLES
    disk,        \* job_store result file: "none" | "honest" (its MAC verifies) | "forged"
    attempt,     \* job_store .attempt file: its count, 0 when absent
    flying,      \* Lanes._flying: proc -> job -> the state of its Future, "none" when absent
    queue,       \* Lanes._queue: proc -> sequence of queued background jobs, each tagged with the
                 \* number of drops that had happened when it took off
    worker,      \* Lanes._worker: proc -> TRUE when it names a thread
    wpc, wjob, wres,          \* the background worker thread of each process
    cpc, cfea, cquick, cres,  \* each caller thread inside Lanes.settle
    seen,        \* what each caller's last settle returned for fea
    peeked,      \* what each caller's last peek returned for fea
    crashes, faults, tampers, stops,
    drops,       \* per process: how many times drop_unstarted dropped the variant's jobs
    shown,       \* how many variant sets still show the variant (variant_sets.store.account_slots)
    up,          \* proc -> TRUE while a server serves in it, FALSE from its death until Start
    stopping,    \* proc -> "no", "closed" after Lanes.close, "removed" after container.stop_owned
    orphans,     \* proc -> the jobs whose containers its dead incarnations left running
    told,        \* ghost: proc -> job -> what the listener saw at its last call: the result the
                 \* run ended with, and whether a result file was on disk
    cut          \* ghost: fea attempts in a row that a crash ended between begin_attempt and
                 \* end_attempt; an attempt that reaches end_attempt resets it

life == <<stops, shown, up, stopping, orphans>>
vars == <<disk, attempt, flying, queue, worker, wpc, wjob, wres,
          cpc, cfea, cquick, cres, seen, peeked, crashes, faults, tampers, drops, told, cut, life>>

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
    /\ crashes = 0 /\ faults = 0 /\ tampers = 0 /\ stops = 0
    /\ drops = [p \in Procs |-> 0] /\ shown = Sets
    /\ up = [p \in Procs |-> TRUE]
    /\ stopping = [p \in Procs |-> "no"]
    /\ orphans = [p \in Procs |-> {}]
    /\ told = [p \in Procs |-> [j \in Jobs |-> Nothing]]
    /\ cut = 0

\* job_store.read: a result counts only when its MAC verifies for <vid>\0<key>.
Stored(j) == disk[j] = "honest"

\* A run after container.stop_owned refuses, or loses its container and raises: either way
\* SandboxUnavailable. The server caused it, so it spends no fault.
RunResults(p) ==
    IF stopping[p] = "removed" THEN {"unavailable"}
    ELSE IF faults < MaxFaults THEN Results ELSE {"ok"}
Spend(p, r) == faults' = IF r = "ok" \/ stopping[p] = "removed" THEN faults ELSE faults + 1

\* The running fea attempt that begin_attempt counted and Lanes._running still names.
\* Lanes.close takes it back, and end_attempt then leaves the count alone.
Counted(p) == wpc[p] \in {"run", "end"} /\ stopping[p] = "no"

\* The containers that process p runs per job key.
RunningIn(p, j) ==
    Cardinality({t \in Threads : t[1] = p /\ j = "quick" /\ cpc[t] = "runquick"})
      + (IF wpc[p] = "run" /\ wjob[p] = j THEN 1 ELSE 0)

FutureOf(r) == CASE r \in {"ok", "timeout"} -> "ok"
                 [] r = "unavailable" -> "error"
                 [] r = "killed" -> "killed"

\* _fly's `with self._lock: del self._flying[path]; future.set_result / set_exception`, one
\* step. Every thread that took that Future sees it settle. A thread holding an unset Future
\* holds the current one, because a Future leaves _flying in the step that settles it.
Settle(p, j, r) ==
    /\ flying' = [flying EXCEPT ![p][j] = "none"]
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

\* _take_off(fea): job_store.read, the _flying lookup, the closed check, _interrupted_too_often,
\* the new Future, the _queue append and the `_worker is None` check, all in one
\* `with self._lock:`. The queued job carries the number of drops so far, which QueuedIsCurrent
\* compares with drops.
FeaTakeOff(t) ==
    LET p == t[1] IN
    /\ up[p]
    /\ cpc[t] = "idle"
    /\ seen' = [seen EXCEPT ![t] = Nothing]
    /\ IF Stored("fea") THEN
            /\ cfea' = [cfea EXCEPT ![t] = [kind |-> "done", value |-> disk["fea"]]]
            /\ UNCHANGED <<flying, queue, worker, wpc>>
       ELSE IF flying[p]["fea"] # "none" THEN
            /\ cfea' = [cfea EXCEPT ![t] = [kind |-> "future", st |-> flying[p]["fea"]]]
            /\ UNCHANGED <<flying, queue, worker, wpc>>
       ELSE IF stopping[p] # "no" THEN
            /\ cfea' = [cfea EXCEPT ![t] = [kind |-> "refused", why |-> "stopped"]]
            /\ UNCHANGED <<flying, queue, worker, wpc>>
       ELSE IF attempt["fea"] >= Cap THEN
            /\ cfea' = [cfea EXCEPT ![t] = [kind |-> "refused", why |-> "interrupted"]]
            /\ UNCHANGED <<flying, queue, worker, wpc>>
       ELSE
            /\ flying' = [flying EXCEPT ![p]["fea"] = "unset"]
            /\ cfea' = [cfea EXCEPT ![t] = [kind |-> "future", st |-> "unset"]]
            /\ queue' = [queue EXCEPT ![p] = Append(@, drops[p])]
            /\ IF ~worker[p]
                 THEN /\ worker' = [worker EXCEPT ![p] = TRUE]
                      /\ wpc' = [wpc EXCEPT ![p] = "get"]
                 ELSE UNCHANGED <<worker, wpc>>
    /\ cpc' = [cpc EXCEPT ![t] = "quick"]
    /\ UNCHANGED <<disk, attempt, wjob, wres, cquick, cres,
                   crashes, faults, tampers, drops, told, cut>>

\* _take_off(quick), one `with self._lock:`. A quick job is never refused.
QuickTakeOff(t) ==
    LET p == t[1] IN
    /\ cpc[t] = "quick"
    /\ IF Stored("quick") THEN
            /\ cquick' = [cquick EXCEPT ![t] = "none"]
            /\ cpc' = [cpc EXCEPT ![t] = "land"]
            /\ UNCHANGED flying
       ELSE IF flying[p]["quick"] # "none" THEN
            /\ cquick' = [cquick EXCEPT ![t] = flying[p]["quick"]]
            /\ cpc' = [cpc EXCEPT ![t] = "waitquick"]
            /\ UNCHANGED flying
       ELSE
            /\ flying' = [flying EXCEPT ![p]["quick"] = "unset"]
            /\ cquick' = [cquick EXCEPT ![t] = "unset"]
            /\ cpc' = [cpc EXCEPT ![t] = "runquick"]
    /\ UNCHANGED <<disk, attempt, queue, worker, wpc, wjob, wres, cfea, cres, seen,
                   crashes, faults, tampers, cut, drops, told>>

\* _fly(quick) -> _attempt -> self._run(job): the quick container, on the caller's thread.
\* Lanes.close leaves the quick lane open, and container.stop_owned ends its runs.
RunQuick(t) ==
    LET p == t[1] IN
    /\ cpc[t] = "runquick"
    /\ \E r \in RunResults(p) :
        /\ cres' = [cres EXCEPT ![t] = r]
        /\ Spend(p, r)
    /\ cpc' = [cpc EXCEPT ![t] = IF cres'[t] = "ok" THEN "writequick" ELSE "settlequick"]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres,
                   cfea, cquick, seen, crashes, tampers, cut, drops, told>>

\* _fly: job_store.write, one os.replace. A raised run skips it, and job_store.write skips a
\* timed-out result (RunQuick sends both of those straight to SettleQuick).
WriteQuick(t) ==
    /\ cpc[t] = "writequick"
    /\ disk' = [disk EXCEPT !["quick"] = "honest"]
    /\ cpc' = [cpc EXCEPT ![t] = "settlequick"]
    /\ UNCHANGED <<attempt, flying, queue, worker, wpc, wjob, wres,
                   cfea, cquick, cres, seen, crashes, faults, tampers, cut, drops, told>>

\* Settle on the caller's own flight. A failed quick run then raises out of settle, so that
\* call returns no card.
SettleQuick(t) ==
    LET p == t[1] IN
    /\ cpc[t] = "settlequick"
    /\ flying' = [flying EXCEPT ![p]["quick"] = "none"]
    /\ cquick' = [u \in Threads |->
            IF u = t THEN "none"
            ELSE IF u[1] = p /\ cquick[u] = "unset" THEN FutureOf(cres[t])
            ELSE cquick[u]]
    /\ cpc' = [cpc EXCEPT ![t] = IF cres[t] \in {"ok", "timeout"} THEN "notifyquick" ELSE "idle"]
    /\ cfea' = [cfea EXCEPT ![t] = IF cres[t] \in {"ok", "timeout"} THEN @ ELSE Nothing]
    /\ cres' = [cres EXCEPT ![t] = IF cres[t] \in {"ok", "timeout"} THEN @ ELSE "ok"]
    /\ UNCHANGED <<disk, attempt, queue, worker, wpc, wjob, wres,
                   seen, crashes, faults, tampers, cut, drops, told>>

\* _fly: the listeners, after `with self._lock:` and outside it, on the thread that ran the job.
\* They see the store as it is then. A listener that raises is logged, so it changes nothing.
\* A failed run skips them (SettleQuick sends it to idle).
NotifyQuick(t) ==
    LET p == t[1] IN
    /\ cpc[t] = "notifyquick"
    /\ told' = [told EXCEPT ![p]["quick"] = [res |-> cres[t], stored |-> disk["quick"] # "none"]]
    /\ cres' = [cres EXCEPT ![t] = "ok"]
    /\ cpc' = [cpc EXCEPT ![t] = "land"]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres,
                   cfea, cquick, seen, crashes, faults, tampers, cut, drops>>

\* settle: quick.result() with no timeout, on a Future another thread flies.
WaitQuick(t) ==
    /\ cpc[t] = "waitquick"
    /\ cquick[t] # "unset"
    /\ cpc' = [cpc EXCEPT ![t] = IF cquick[t] = "ok" THEN "land" ELSE "idle"]
    /\ cfea' = [cfea EXCEPT ![t] = IF cquick[t] = "ok" THEN @ ELSE Nothing]
    /\ cquick' = [cquick EXCEPT ![t] = "none"]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres,
                   cres, seen, crashes, faults, tampers, cut, drops, told>>

\* _land(fea): Done, Pending when the wait runs out first, or Refused on SandboxUnavailable or
\* Superseded.
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
             \/ /\ cfea[t].st = "dropped"
                /\ seen' = [seen EXCEPT ![t] = [kind |-> "refused", why |-> "superseded"]]
             \/ /\ cfea[t].st = "killed"
                /\ UNCHANGED seen
    /\ cpc' = [cpc EXCEPT ![t] = "idle"]
    /\ cfea' = [cfea EXCEPT ![t] = Nothing]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres,
                   cquick, cres, crashes, faults, tampers, cut, drops, told>>

\* Lanes.peek, for the scorecard operation: job_store.read of quick, then _look for fea in one
\* `with self._lock:`: job_store.read, the _flying lookup, then unfinished_runs against the
\* cap. A job flying here is pending, though its own attempt may have reached the cap. No wait,
\* and no job started.
Peek(t) ==
    LET p == t[1] IN
    /\ Peeks
    /\ up[p]
    /\ cpc[t] = "idle"
    /\ Stored("quick")
    /\ peeked' = [peeked EXCEPT ![t] =
                 IF Stored("fea") THEN [kind |-> "done", value |-> disk["fea"]]
                 ELSE IF flying[p]["fea"] = "none" /\ attempt["fea"] >= Cap
                   THEN [kind |-> "refused", why |-> "interrupted"]
                 ELSE [kind |-> "pending"]]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres, cpc, cfea, cquick,
                   cres, seen, crashes, faults, tampers, cut, drops, told, life>>

-----------------------------------------------------------------------------
(* Lanes._drain, the background worker thread of process p.                *)

\* `with self._lock:` over `while not self._queue: self._wake.wait()` and `popleft()`. From here
\* the job is started, and drop_unstarted can no longer reach it.
WorkerGet(p) ==
    /\ wpc[p] = "get"
    /\ queue[p] # <<>>
    /\ wjob' = [wjob EXCEPT ![p] = "fea"]
    /\ queue' = [queue EXCEPT ![p] = Tail(@)]
    /\ wpc' = [wpc EXCEPT ![p] = "begin"]
    /\ UNCHANGED <<disk, attempt, flying, worker, wres, cpc, cfea, cquick, cres, seen,
                   crashes, faults, tampers, cut, drops, told>>

\* _attempt, in one `with self._lock:`: on a closed Lanes it raises SandboxUnavailable, else
\* job_store.begin_attempt writes unfinished_runs + 1 with one os.replace and _running names
\* the job.
WorkerBegin(p) ==
    /\ wpc[p] = "begin"
    /\ IF stopping[p] = "no"
         THEN /\ attempt' = [attempt EXCEPT ![wjob[p]] = @ + 1]
              /\ wpc' = [wpc EXCEPT ![p] = "run"]
              /\ UNCHANGED wres
         ELSE /\ wres' = [wres EXCEPT ![p] = "unavailable"]
              /\ wpc' = [wpc EXCEPT ![p] = "settle"]
              /\ UNCHANGED attempt
    /\ UNCHANGED <<disk, flying, queue, worker, wjob, cpc, cfea, cquick, cres,
                   seen, crashes, faults, tampers, cut, drops, told>>

\* _attempt: self._run(job), the background container.
WorkerRun(p) ==
    /\ wpc[p] = "run"
    /\ \E r \in RunResults(p) :
        /\ wres' = [wres EXCEPT ![p] = r]
        /\ Spend(p, r)
    /\ wpc' = [wpc EXCEPT ![p] = "end"]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wjob, cpc, cfea, cquick,
                   cres, seen, crashes, tampers, cut, drops, told>>

\* _attempt finally, in one `with self._lock:`: while _running still names the job,
\* job_store.end_attempt unlinks the .attempt file. After Lanes.close it does not.
WorkerEnd(p) ==
    /\ wpc[p] = "end"
    /\ IF stopping[p] = "no"
         THEN /\ attempt' = [attempt EXCEPT ![wjob[p]] = 0]
              /\ cut' = IF wjob[p] = "fea" THEN 0 ELSE cut
         ELSE UNCHANGED <<attempt, cut>>
    /\ wpc' = [wpc EXCEPT ![p] = IF wres[p] = "ok" THEN "write" ELSE "settle"]
    /\ UNCHANGED <<disk, flying, queue, worker, wjob, wres, cpc, cfea, cquick, cres,
                   seen, crashes, faults, tampers, drops, told>>

\* _fly: job_store.write. A raised run skips it, and job_store.write skips a timed-out one.
WorkerWrite(p) ==
    /\ wpc[p] = "write"
    /\ disk' = [disk EXCEPT ![wjob[p]] = "honest"]
    /\ wpc' = [wpc EXCEPT ![p] = "settle"]
    /\ UNCHANGED <<attempt, flying, queue, worker, wjob, wres, cpc, cfea, cquick,
                   cres, seen, crashes, faults, tampers, cut, drops, told>>

\* A BaseException then leaves _drain's loop. A run that stored or timed out goes on to the
\* listeners.
WorkerSettle(p) ==
    /\ wpc[p] = "settle"
    /\ Settle(p, wjob[p], wres[p])
    /\ wpc' = [wpc EXCEPT ![p] = CASE wres[p] \in {"ok", "timeout"} -> "notify"
                                    [] wres[p] = "killed" -> "exit"
                                    [] OTHER -> "get"]
    /\ wres' = [wres EXCEPT ![p] = IF wres[p] \in {"ok", "timeout"} THEN @ ELSE "ok"]
    /\ UNCHANGED <<disk, attempt, queue, worker, wjob, cpc, cres,
                   seen, crashes, faults, tampers, cut, drops, told>>

\* _fly: the listeners, as NotifyQuick says.
WorkerNotify(p) ==
    /\ wpc[p] = "notify"
    /\ told' = [told EXCEPT ![p][wjob[p]] = [res |-> wres[p], stored |-> disk[wjob[p]] # "none"]]
    /\ wres' = [wres EXCEPT ![p] = "ok"]
    /\ wpc' = [wpc EXCEPT ![p] = "get"]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wjob, cpc, cfea, cquick, cres,
                   seen, crashes, faults, tampers, cut, drops>>

\* _drain finally: `with self._lock: self._worker = None; if queued: self._start_worker()`.
WorkerExit(p) ==
    /\ wpc[p] = "exit"
    /\ IF queue[p] # <<>>
         THEN /\ worker' = [worker EXCEPT ![p] = TRUE]
              /\ wpc' = [wpc EXCEPT ![p] = "get"]
         ELSE /\ worker' = [worker EXCEPT ![p] = FALSE]
              /\ wpc' = [wpc EXCEPT ![p] = "gone"]
    /\ UNCHANGED <<disk, attempt, flying, queue, wjob, wres, cpc, cfea, cquick, cres,
                   seen, crashes, faults, tampers, cut, drops, told>>

-----------------------------------------------------------------------------
(* What the world does.                                                    *)

\* Lanes._refuse_locked over the queue: the queued fea job leaves _flying and its Future gets
\* `how`, which wakes every caller waiting on it. A job a worker already took is not queued.
RefuseQueued(p, how) ==
    IF queue[p] # <<>>
      THEN /\ flying' = [flying EXCEPT ![p]["fea"] = "none"]
           /\ cfea' = [t \in Threads |->
                 IF t[1] = p /\ cfea[t] = [kind |-> "future", st |-> "unset"]
                   THEN [kind |-> "future", st |-> how] ELSE cfea[t]]
      ELSE UNCHANGED <<flying, cfea>>

\* A newer revision replaces the variant in one set's slot. variant_sets.store calls
\* Lanes.drop_unstarted, which in one `with self._lock:` reads every set of the account and,
\* when none still shows the variant, gives every queued job of the variant Superseded. A
\* variant another brief's set still shows keeps its queued job.
Replace(p) ==
    /\ up[p]
    /\ shown > 0
    /\ shown' = shown - 1
    /\ IF shown = 1
         THEN /\ drops' = [drops EXCEPT ![p] = @ + 1]
              /\ queue' = [queue EXCEPT ![p] = <<>>]
              /\ RefuseQueued(p, "dropped")
         ELSE UNCHANGED <<drops, queue, flying, cfea>>
    /\ UNCHANGED <<disk, attempt, worker, wpc, wjob, wres, cpc, cquick, cres, seen, peeked,
                   crashes, faults, tampers, told, cut, stops, up, stopping, orphans>>

\* The server stops: Lanes.close, which src/cad/server/stopping.py calls on SIGTERM or when the
\* stdio server ends, in one `with self._lock:`. A background take-off is refused from now on,
\* the queued job is refused, and the running attempt is taken back: the server ends that run,
\* not the job. job_store.undo_attempt never takes the count below 0.
Close(p) ==
    /\ up[p] /\ stopping[p] = "no"
    /\ stops < MaxStops
    /\ stops' = stops + 1
    /\ stopping' = [stopping EXCEPT ![p] = "closed"]
    /\ queue' = [queue EXCEPT ![p] = <<>>]
    /\ RefuseQueued(p, "error")
    /\ attempt' = IF Counted(p) THEN [attempt EXCEPT ![wjob[p]] = IF @ > 0 THEN @ - 1 ELSE 0]
                  ELSE attempt
    /\ UNCHANGED <<disk, worker, wpc, wjob, wres, cpc, cquick, cres, seen, peeked,
                   crashes, faults, tampers, drops, told, cut, shown, up, orphans>>

\* container.stop_owned: set `stopping`, so every later run refuses, then remove the containers
\* this process started, so a run whose container it removed raises (RunResults).
StopOwned(p) ==
    /\ up[p] /\ stopping[p] = "closed"
    /\ stopping' = [stopping EXCEPT ![p] = "removed"]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres, cpc, cfea, cquick, cres,
                   seen, peeked, crashes, faults, tampers, drops, told, cut, stops, shown, up,
                   orphans>>

\* The process dies. Its futures, queue, worker and callers are gone, and the store keeps every
\* file.
Die(p) ==
    /\ up' = [up EXCEPT ![p] = FALSE]
    /\ stopping' = [stopping EXCEPT ![p] = "no"]
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
    /\ told' = [told EXCEPT ![p] = [j \in Jobs |-> Nothing]]
    /\ UNCHANGED <<disk, attempt, faults, tampers, drops, shown>>

\* The SIGTERM handler raises SIGTERM again with the default action, after Close and StopOwned,
\* so the process dies with its attempt taken back and its containers gone.
Exit(p) ==
    /\ up[p] /\ stopping[p] = "removed"
    /\ Die(p)
    /\ UNCHANGED <<crashes, cut, stops, orphans>>

\* The process dies without ending its checks: SIGKILL, an out-of-memory kill, or a stop that
\* outlasted systemd's timeout. Every container it still runs keeps running as an orphan.
Crash(p) ==
    /\ up[p] /\ crashes < MaxCrashes
    /\ crashes' = crashes + 1
    /\ cut' = IF Counted(p) /\ wjob[p] = "fea" THEN cut + 1 ELSE cut
    /\ orphans' = [orphans EXCEPT ![p] =
                     IF stopping[p] = "removed" THEN @
                     ELSE @ \cup {j \in Jobs : RunningIn(p, j) > 0}]
    /\ Die(p)
    /\ UNCHANGED stops

\* A server starts in the dead one's place. Before it serves a call, container.remove_orphans
\* removes every container whose owner pid is dead, running or not.
Start(p) ==
    /\ ~up[p]
    /\ up' = [up EXCEPT ![p] = TRUE]
    /\ orphans' = [q \in Procs |-> {}]
    /\ UNCHANGED <<disk, attempt, flying, queue, worker, wpc, wjob, wres, cpc, cfea, cquick, cres,
                   seen, peeked, crashes, faults, tampers, drops, told, cut, stops, shown,
                   stopping>>

\* Someone without the store key overwrites a result file.
Tamper(j) ==
    /\ tampers < MaxTampers
    /\ tampers' = tampers + 1
    /\ disk' = [disk EXCEPT ![j] = "forged"]
    /\ UNCHANGED <<attempt, flying, queue, worker, wpc, wjob, wres,
                   cpc, cfea, cquick, cres, seen, peeked, crashes, faults, cut, drops, told, life>>

\* Only Peek and Die change peeked.
CallerStep(t) ==
    /\ \/ FeaTakeOff(t) \/ QuickTakeOff(t) \/ RunQuick(t) \/ WriteQuick(t) \/ SettleQuick(t)
       \/ NotifyQuick(t) \/ WaitQuick(t) \/ Land(t)
    /\ UNCHANGED <<peeked, life>>

WorkerStep(p) ==
    /\ \/ WorkerGet(p) \/ WorkerBegin(p) \/ WorkerRun(p) \/ WorkerEnd(p) \/ WorkerWrite(p)
       \/ WorkerSettle(p) \/ WorkerNotify(p) \/ WorkerExit(p)
    /\ UNCHANGED <<peeked, life>>

\* What a stop or a death leads to: a stop that began runs to its end, and a dead server is
\* started again (systemd restarts it, or the person opens a new session).
Lifecycle(p) == StopOwned(p) \/ Exit(p) \/ Start(p)

Next ==
    \/ \E t \in Threads : CallerStep(t) \/ Peek(t)
    \/ \E p \in Procs : WorkerStep(p) \/ Crash(p) \/ Replace(p) \/ Close(p) \/ Lifecycle(p)
    \/ \E j \in Jobs : Tamper(j)

\* Callers keep polling, as the server instructions tell the agent to while a check is pending.
\* Peek has no fairness: a scorecard read is optional, and settle is what moves a job. Close has
\* none either: a server need never stop.
Fairness ==
    /\ \A t \in Threads : WF_vars(CallerStep(t))
    /\ \A p \in Procs : WF_vars(WorkerStep(p))
    /\ \A p \in Procs : WF_vars(Lifecycle(p))

Spec == Init /\ [][Next]_vars /\ Fairness

-----------------------------------------------------------------------------
(* Properties.                                                             *)

Handles ==
    {Nothing, [kind |-> "pending"]}
      \cup [kind : {"future"}, st : FutureStates]
      \cup [kind : {"done"}, value : {"honest", "forged"}]
      \cup [kind : {"refused"}, why : {"interrupted", "unavailable", "superseded", "stopped"}]

TypeOK ==
    /\ disk \in [Jobs -> {"none", "honest", "forged"}]
    /\ attempt \in [Jobs -> Nat]
    /\ flying \in [Procs -> [Jobs -> FutureStates]]
    /\ DOMAIN queue = Procs /\ \A p \in Procs : queue[p] \in Seq(0..Sets)
    /\ worker \in [Procs -> BOOLEAN]
    /\ wpc \in [Procs -> {"gone", "get", "begin", "run", "end", "write", "settle",
                          "notify", "exit"}]
    /\ wjob \in [Procs -> Jobs]
    /\ wres \in [Procs -> Results]
    /\ cpc \in [Threads -> {"idle", "quick", "runquick", "writequick", "settlequick",
                            "notifyquick", "waitquick", "land"}]
    /\ cfea \in [Threads -> Handles]
    /\ cquick \in [Threads -> FutureStates]
    /\ cres \in [Threads -> Results]
    /\ seen \in [Threads -> Handles]
    /\ peeked \in [Threads -> Handles]
    /\ crashes \in 0..MaxCrashes /\ faults \in 0..MaxFaults /\ tampers \in 0..MaxTampers
    /\ stops \in 0..MaxStops
    /\ cut \in 0..MaxCrashes
    /\ drops \in [Procs -> 0..Sets] /\ shown \in 0..Sets
    /\ up \in [Procs -> BOOLEAN]
    /\ stopping \in [Procs -> {"no", "closed", "removed"}]
    /\ orphans \in [Procs -> SUBSET Jobs]
    /\ told \in [Procs -> [Jobs -> {Nothing} \cup [res : Results, stored : BOOLEAN]]]

\* No duplicate container: in each process, at most one container runs per job key, counting
\* the ones its dead incarnations left running.
OneContainerPerKey ==
    \A p \in Procs, j \in Jobs : RunningIn(p, j) + (IF j \in orphans[p] THEN 1 ELSE 0) <= 1

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

\* A drop leaves no job queued from before it in that process: every queued job took off after
\* the last drop, so no container starts for a variant that left its last set while its job
\* waited.
QueuedIsCurrent ==
    \A p \in Procs : \A i \in 1..Len(queue[p]) : queue[p][i] = drops[p]

\* A queued job is dropped only once no variant set shows its variant, so a newer revision in
\* one brief never drops a check that another brief's set still shows and waits on.
KeptWhileShown ==
    \A t \in Threads :
        /\ cfea[t] = [kind |-> "future", st |-> "dropped"] => shown = 0
        /\ seen[t] = [kind |-> "refused", why |-> "superseded"] => shown = 0

\* A listener is called only after the job's result is on disk, so a snapshot it takes then holds
\* that result. A timed-out run stores none.
NotifiedAfterStore ==
    \A p \in Procs, j \in Jobs :
        told[p][j] # Nothing => (told[p][j].res = "ok" => told[p][j].stored)

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
