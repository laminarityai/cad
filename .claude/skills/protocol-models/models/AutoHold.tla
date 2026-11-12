------------------------------ MODULE AutoHold ------------------------------
(***************************************************************************)
(* A stop holds its conversation until the person acts, for one account,  *)
(* one project and one brief: conversations/store.py (record_event,       *)
(* start_run, lift_hold), operations/tenants.bind, auto/gate.py (gate,     *)
(* record_proposals), operations/auto.py (auto_start, auto_ask, auto_stop) *)
(* and chat/routes.py (Chat._begin and catch_up's restart heal).           *)
(*                                                                         *)
(* The run logs and the conversation records are on disk. Every write of   *)
(* them takes store._LOCK, so each write is one step, except that a crash  *)
(* can fall between a run's stop and its conversation write. A turn's tool *)
(* calls run one at a time. auto_start reads the brief three times outside *)
(* the lock, so those reads are three steps, and any caller may propose    *)
(* between them.                                                           *)
(***************************************************************************)
EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS
    Convs,         \* web app conversations of the account
    MaxRuns,       \* runs of the brief
    MaxProposals,  \* propose_requirements calls on the brief, from any caller
    MaxActs,       \* messages and delivered page answers per conversation
    MaxCrashes

VARIABLES
    \* On disk.
    props,      \* the brief's proposals in order: "proposed", "confirmed" or "declined"
    runs,       \* the brief's runs in order, each [conv, state, wm, dec]
    auto,       \* Conversation.auto_run: a run's number, or 0
    stopped,    \* Conversation.stopped_run: a run's number, or 0
    tail,       \* the transcript's last event: "none", "message", "delivery" or "agent"
    tailAct,    \* the person act that appended the transcript's last message or delivery
    \* In memory, lost on a crash.
    running,    \* Channel.running
    begin,      \* Chat._begin: "idle", or "half" between lift_hold and the append
    startAt,    \* auto_start: 0 for none, 1..3 for its next read in ReadOrder, 4 for start_run
    swm,        \* the watermark auto_start read
    sdec,       \* the confirmed proposal auto_start read, 0 for none
    \* Ghosts.
    acts,       \* person acts begun in the conversation
    on,         \* the act the running turn serves
    acted,      \* the person acted since the conversation's last stop
    holdAt,     \* acts when the conversation's last stop happened
    untouched,  \* a crash cut a stop before its conversation write, and no call came since
    pastStop,       \* a build passed the gate before the person acted after a stop
    startPastStop,  \* a run started before the person acted after a stop
    pendingBuild,   \* a build passed a run's gate while a proposal waited for the person
    staleBuild,     \* a build passed a run's gate under a confirmed set the run did not read
    \* Bounds.
    crashes

disk == <<props, runs, auto, stopped, tail, tailAct>>
memory == <<running, begin, startAt, swm, sdec>>
flags == <<pastStop, startPastStop, pendingBuild, staleBuild>>
ghost == <<acts, on, acted, holdAt, untouched, flags>>
vars == <<disk, memory, ghost, crashes>>

Kinds == {"message", "delivery"}

\* operations/auto.py auto_start: the watermark, then the pending check, then the confirmed set.
ReadOrder == <<"watermark", "pending", "confirmed">>

Max(S) == CHOOSE x \in S : \A y \in S : y <= x

\* BriefState.latest is PROPOSED. A newer proposal supersedes an older one, so only the latest
\* can be answered.
Pending == Len(props) > 0 /\ props[Len(props)] = "proposed"

\* BriefState.confirmed: the newest confirmed proposal, 0 for none.
Decision ==
    LET found == {i \in 1..Len(props) : props[i] = "confirmed"}
    IN IF found = {} THEN 0 ELSE Max(found)

RunningRuns == {r \in 1..Len(runs) : runs[r].state = "running"}

\* tenants.bind: the conversation's running run, or else the stopped run that holds it.
Bound(c) == IF auto[c] # 0 THEN auto[c] ELSE stopped[c]

\* A current run that stopped before its conversation was written.
Stale(c) == auto[c] # 0 /\ runs[auto[c]].state = "stopped"

Init ==
    /\ props = <<>>
    /\ runs = <<>>
    /\ auto = [c \in Convs |-> 0]
    /\ stopped = [c \in Convs |-> 0]
    /\ tail = [c \in Convs |-> "none"]
    /\ tailAct = [c \in Convs |-> 0]
    /\ running = [c \in Convs |-> FALSE]
    /\ begin = [c \in Convs |-> "idle"]
    /\ startAt = [c \in Convs |-> 0]
    /\ swm = [c \in Convs |-> 0]
    /\ sdec = [c \in Convs |-> 0]
    /\ acts = [c \in Convs |-> 0]
    /\ on = [c \in Convs |-> 0]
    /\ acted = [c \in Convs |-> TRUE]
    /\ holdAt = [c \in Convs |-> 0]
    /\ untouched = [c \in Convs |-> FALSE]
    /\ pastStop = FALSE /\ startPastStop = FALSE
    /\ pendingBuild = FALSE /\ staleBuild = FALSE
    /\ crashes = 0

-----------------------------------------------------------------------------
(* The run log and the conversation record, under store._LOCK.            *)

\* record_event's write after a stop: _held_by when the run is its conversation's current run.
HoldFor(r) ==
    LET c == runs[r].conv IN
    IF auto[c] = r
    THEN /\ auto' = [auto EXCEPT ![c] = 0]
         /\ stopped' = [stopped EXCEPT ![c] = r]
    ELSE UNCHANGED <<auto, stopped>>

\* The ghosts of a stop: the person has not acted since.
Halt(r) ==
    LET c == runs[r].conv IN
    /\ acted' = [acted EXCEPT ![c] = FALSE]
    /\ holdAt' = [holdAt EXCEPT ![c] = acts[c]]

\* record_event with an event that stops a running run. append_event records nothing on a
\* stopped run, and the write still holds the conversation, so a crash before it heals here.
Record(r) ==
    IF runs[r].state = "running"
    THEN /\ runs' = [runs EXCEPT ![r].state = "stopped"]
         /\ HoldFor(r)
         /\ Halt(r)
    ELSE /\ HoldFor(r)
         /\ UNCHANGED <<runs, acted, holdAt>>

\* lift_hold: let go of a current run that already stopped, and clear the stopped run.
LiftHold(c) ==
    /\ auto' = [auto EXCEPT ![c] = IF Stale(c) THEN 0 ELSE @]
    /\ stopped' = [stopped EXCEPT ![c] = 0]
    /\ untouched' = [untouched EXCEPT ![c] = FALSE]

\* The memory a crash loses: no turn runs, no _begin or auto_start is half done.
Lost ==
    /\ running' = [c \in Convs |-> FALSE]
    /\ begin' = [c \in Convs |-> "idle"]
    /\ startAt' = [c \in Convs |-> 0]
    /\ swm' = [c \in Convs |-> 0]
    /\ sdec' = [c \in Convs |-> 0]
    /\ on' = [c \in Convs |-> 0]
    /\ crashes' = crashes + 1

-----------------------------------------------------------------------------
(* Any caller, and the person.                                             *)

\* propose_requirements on the brief, from this conversation, another one or an outside client.
Propose ==
    /\ Len(props) < MaxProposals
    /\ props' = Append(props, "proposed")
    /\ UNCHANGED <<runs, auto, stopped, tail, tailAct, memory, ghost, crashes>>

\* The person answers the latest proposal on the confirmation page.
Answer ==
    /\ Pending
    /\ \E a \in {"confirmed", "declined"} : props' = [props EXCEPT ![Len(props)] = a]
    /\ UNCHANGED <<runs, auto, stopped, tail, tailAct, memory, ghost, crashes>>

\* auto_stop: the person presses Stop on a run, any time.
Stop(r) ==
    /\ Record(r)
    /\ UNCHANGED <<props, tail, tailAct, memory, acts, on, untouched, flags, crashes>>

\* A run stops, by any reason, and the process dies before record_event writes the conversation.
StopCrash(r) ==
    /\ runs[r].state = "running" /\ crashes < MaxCrashes
    /\ runs' = [runs EXCEPT ![r].state = "stopped"]
    /\ Halt(r)
    /\ untouched' = [untouched EXCEPT ![runs[r].conv] = TRUE]
    /\ Lost
    /\ UNCHANGED <<props, auto, stopped, tail, tailAct, acts, flags>>

Crash ==
    /\ crashes < MaxCrashes
    /\ Lost
    /\ UNCHANGED <<disk, acts, acted, holdAt, untouched, flags>>

\* Chat._begin, which Chat.start (a message) and Chat._deliver (a page answer) call while no turn
\* runs: lift_hold, then the append, then _run. Begin is the person's act.
Lifted(c) == LiftHold(c) /\ UNCHANGED <<tail, tailAct>>

AppendEvent(c, kind) ==
    /\ tail' = [tail EXCEPT ![c] = kind]
    /\ tailAct' = [tailAct EXCEPT ![c] = acts'[c]]

Appended(c) == \E kind \in Kinds : AppendEvent(c, kind) /\ UNCHANGED <<auto, stopped, untouched>>

First(c) == Lifted(c)
Second(c) == Appended(c)

Begin(c) ==
    /\ ~running[c] /\ begin[c] = "idle" /\ acts[c] < MaxActs
    /\ begin' = [begin EXCEPT ![c] = "half"]
    /\ acts' = [acts EXCEPT ![c] = @ + 1]
    /\ acted' = [acted EXCEPT ![c] = TRUE]
    /\ First(c)
    /\ UNCHANGED <<props, runs, running, startAt, swm, sdec, on, holdAt, flags, crashes>>

Run(c) ==
    /\ begin[c] = "half"
    /\ UNCHANGED <<props, runs, startAt, swm, sdec, acts, acted, holdAt, flags, crashes>>
    /\ begin' = [begin EXCEPT ![c] = "idle"]
    /\ Second(c)
    /\ running' = [running EXCEPT ![c] = TRUE]
    /\ on' = [on EXCEPT ![c] = acts[c]]

\* catch_up's restart heal: a delivery tail and no turn, so the delivery's turn runs again. It is
\* not a person act, because the person may have pressed Stop after the delivery.
Heal(c) ==
    /\ ~running[c] /\ begin[c] = "idle" /\ tail[c] = "delivery"
    /\ running' = [running EXCEPT ![c] = TRUE]
    /\ on' = [on EXCEPT ![c] = tailAct[c]]
    /\ UNCHANGED <<auto, stopped, untouched>>
    /\ UNCHANGED <<props, runs, tail, tailAct, begin, startAt, swm, sdec, acts, acted, holdAt,
                   flags, crashes>>

-----------------------------------------------------------------------------
(* The agent of a running turn, one tool call at a time.                   *)

Idle(c) == running[c] /\ startAt[c] = 0

Touch(c) == tail' = [tail EXCEPT ![c] = "agent"]

\* build_variant, score_variant or auto_revise: bind, then gate. bind reads the conversation
\* without the lock, but only this conversation's agent starts a run in it, and a person act waits
\* for the turn to end, so the read and the gate are one step. The gate's record_proposals records
\* Proposed, which stops the run, when a proposal came after the watermark.
Build(c) ==
    /\ Idle(c)
    /\ LET r == Bound(c) IN
       IF r = 0 THEN
           /\ pastStop' = (pastStop \/ ~acted[c])
           /\ UNCHANGED <<runs, auto, stopped, acted, holdAt, pendingBuild, staleBuild>>
       ELSE IF runs[r].state = "running" /\ Len(props) = runs[r].wm THEN
           /\ pastStop' = (pastStop \/ ~acted[c])
           /\ pendingBuild' = (pendingBuild \/ Pending)
           /\ staleBuild' = (staleBuild \/ Decision # runs[r].dec)
           /\ UNCHANGED <<runs, auto, stopped, acted, holdAt>>
       ELSE
           /\ Record(r) \* RunStopped
           /\ UNCHANGED <<pastStop, pendingBuild, staleBuild>>
    /\ Touch(c)
    /\ untouched' = [untouched EXCEPT ![c] = FALSE]
    /\ UNCHANGED <<props, tailAct, memory, acts, on, startPastStop, crashes>>

\* auto_ask on the bound run: _refuse_unless_held, then record_event(AgentAsked).
Ask(c) ==
    /\ Idle(c) /\ Bound(c) # 0
    /\ Record(Bound(c))
    /\ Touch(c)
    /\ untouched' = [untouched EXCEPT ![c] = FALSE]
    /\ UNCHANGED <<props, tailAct, memory, acts, on, flags, crashes>>

StartCall(c) ==
    /\ Idle(c)
    /\ startAt' = [startAt EXCEPT ![c] = 1]
    /\ Touch(c)
    /\ UNCHANGED <<props, runs, auto, stopped, tailAct, running, begin, swm, sdec, ghost, crashes>>

\* auto_start's reads of the brief, outside the lock: the watermark, the pending check, and the
\* confirmed set, which must hold a requirement a check decides.
Read(c) ==
    /\ running[c] /\ startAt[c] \in 1..3
    /\ LET what == ReadOrder[startAt[c]]
           next == [startAt EXCEPT ![c] = @ + 1]
           refused == [startAt EXCEPT ![c] = 0]
       IN CASE what = "watermark" ->
                 /\ swm' = [swm EXCEPT ![c] = Len(props)]
                 /\ startAt' = next
                 /\ UNCHANGED sdec
            [] what = "pending" ->
                 /\ startAt' = IF Pending THEN refused ELSE next
                 /\ UNCHANGED <<swm, sdec>>
            [] what = "confirmed" ->
                 /\ sdec' = [sdec EXCEPT ![c] = Decision]
                 /\ startAt' = IF Decision = 0 THEN refused ELSE next
                 /\ UNCHANGED swm
    /\ UNCHANGED <<disk, running, begin, ghost, crashes>>

\* start_run under _LOCK: hold the conversation for a current run that already stopped, refuse
\* while a stop holds it, then open_under_lock. That returns the brief's running run to its own
\* conversation, refuses it to another (RunNotHeld), or creates the next run. record_proposals
\* stops a new run at once when a proposal came after its watermark, and so do conflicting bounds.
Open(c) ==
    /\ running[c] /\ startAt[c] = 4
    /\ startAt' = [startAt EXCEPT ![c] = 0]
    /\ untouched' = [untouched EXCEPT ![c] = FALSE]
    /\ LET a1 == IF Stale(c) THEN 0 ELSE auto[c]
           s1 == IF Stale(c) THEN auto[c] ELSE stopped[c]
       IN IF s1 # 0 \/ RunningRuns # {} \/ Len(runs) = MaxRuns THEN
              /\ auto' = [auto EXCEPT ![c] = a1]
              /\ stopped' = [stopped EXCEPT ![c] = s1]
              /\ UNCHANGED <<runs, acted, holdAt, startPastStop>>
          ELSE \E conflict \in BOOLEAN :
              LET n == Len(runs) + 1
                  stops == conflict \/ Len(props) > swm[c]
              IN /\ runs' = Append(runs, [conv |-> c, state |-> IF stops THEN "stopped" ELSE "running",
                                          wm |-> swm[c], dec |-> sdec[c]])
                 /\ auto' = [auto EXCEPT ![c] = IF stops THEN 0 ELSE n]
                 /\ stopped' = [stopped EXCEPT ![c] = IF stops THEN n ELSE s1]
                 /\ startPastStop' = (startPastStop \/ ~acted[c])
                 /\ IF stops
                    THEN /\ acted' = [acted EXCEPT ![c] = FALSE]
                         /\ holdAt' = [holdAt EXCEPT ![c] = acts[c]]
                    ELSE UNCHANGED <<acted, holdAt>>
    /\ UNCHANGED <<props, tail, tailAct, running, begin, swm, sdec, acts, on, pastStop,
                   pendingBuild, staleBuild, crashes>>

\* The turn ends, after appending at least one event.
EndTurn(c) ==
    /\ Idle(c)
    /\ running' = [running EXCEPT ![c] = FALSE]
    /\ on' = [on EXCEPT ![c] = 0]
    /\ Touch(c)
    /\ UNCHANGED <<props, runs, auto, stopped, tailAct, begin, startAt, swm, sdec, acts, acted,
                   holdAt, untouched, flags, crashes>>

\* Nothing runs and nothing is half done.
Finished ==
    /\ \A c \in Convs : ~running[c] /\ begin[c] = "idle"
    /\ UNCHANGED vars

Next ==
    \/ Propose \/ Answer \/ Crash \/ Finished
    \/ \E r \in 1..Len(runs) : Stop(r) \/ StopCrash(r)
    \/ \E c \in Convs :
        \/ Begin(c) \/ Run(c) \/ Heal(c)
        \/ Build(c) \/ Ask(c) \/ StartCall(c) \/ Read(c) \/ Open(c) \/ EndTurn(c)

Spec == Init /\ [][Next]_vars

Conversations == Permutations(Convs)

-----------------------------------------------------------------------------
(* Properties.                                                             *)

RunRecords ==
    [conv : Convs, state : {"running", "stopped"}, wm : 0..MaxProposals, dec : 0..MaxProposals]

TypeOK ==
    /\ props \in Seq({"proposed", "confirmed", "declined"}) /\ Len(props) <= MaxProposals
    /\ runs \in Seq(RunRecords) /\ Len(runs) <= MaxRuns
    /\ auto \in [Convs -> 0..MaxRuns] /\ stopped \in [Convs -> 0..MaxRuns]
    /\ tail \in [Convs -> {"none", "agent"} \cup Kinds]
    /\ tailAct \in [Convs -> 0..MaxActs]
    /\ running \in [Convs -> BOOLEAN]
    /\ begin \in [Convs -> {"idle", "half"}]
    /\ startAt \in [Convs -> 0..4]
    /\ swm \in [Convs -> 0..MaxProposals] /\ sdec \in [Convs -> 0..MaxProposals]
    /\ acts \in [Convs -> 0..MaxActs] /\ on \in [Convs -> 0..MaxActs]
    /\ acted \in [Convs -> BOOLEAN] /\ holdAt \in [Convs -> 0..MaxActs]
    /\ untouched \in [Convs -> BOOLEAN]
    /\ {pastStop, startPastStop, pendingBuild, staleBuild} \subseteq BOOLEAN
    /\ crashes \in 0..MaxCrashes

\* After any stop, no build or score passes the gate in that conversation until the person acts.
NoBuildPastAStop == ~pastStop

\* After any stop, no run starts in that conversation until the person acts.
NoRunWithoutAPersonStep == ~startPastStop

\* Only the person's act, in Chat._begin, clears the stopped run. No tool call and no restart
\* heal does.
OnlyAPersonStepReopens ==
    [][\A c \in Convs : stopped[c] # 0 /\ stopped'[c] = 0 => "half" \in {begin[c], begin'[c]}]_vars

\* A stopped run never runs again.
StopSticks ==
    [][\A r \in 1..Len(runs) : runs[r].state = "stopped" => runs'[r].state = "stopped"]_vars

\* A running run is its conversation's current run, so a conversation has at most one.
OneRunningRunPerConversation == \A r \in RunningRuns : auto[runs[r].conv] = r

\* A conversation binds only its own runs, so only it drives them.
OnlyTheOwnerDrives == \A c \in Convs : Bound(c) # 0 => runs[Bound(c)].conv = c

\* No build passes a run's gate while a proposal on its brief waits for the person.
NoBuildUnderAPendingProposal == ~pendingBuild

\* A build under a run is judged against the confirmed set the run started from.
BuiltUnderItsDecision == ~staleBuild

\* A turn that serves a person act runs held only by a stop that came after the act began.
ActedLiftsTheHold ==
    \A c \in Convs : running[c] /\ stopped[c] # 0 => holdAt[c] >= on[c]

\* A stop that a crash cut before its conversation write is healed by the next call.
HealedByTheNextCall == \A c \in Convs : Stale(c) => untouched[c]

=============================================================================
