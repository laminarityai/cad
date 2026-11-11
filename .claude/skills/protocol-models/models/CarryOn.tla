------------------------------ MODULE CarryOn ------------------------------
(***************************************************************************)
(* The chat carries on after the person answers the confirmation page, for *)
(* one account and one project: chat/routes.py (Chat._deliver, answered,   *)
(* catch_up, the done callback), chat/answer_driver.py (waiting_on,        *)
(* told_through, delivery, settle), conversations/store.confirmed,         *)
(* operations/confirmation.ask_to_confirm (answers_recorded) and           *)
(* confirmations/web.py record (the on_recorded hook).                     *)
(*                                                                         *)
(* The transcript is the claim. What a conversation was told is derived    *)
(* from its own transcript, which survives a crash with the ledger. The    *)
(* running flag, the channel cache, the pending hook calls and the done    *)
(* callbacks live in the server's memory and are lost on a crash. Every    *)
(* _deliver runs synchronously on the one event loop, from its running     *)
(* check to its append, so each one is a single step.                      *)
(***************************************************************************)
EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS
    Convs,         \* conversations of the account, all on the one project
    MaxAnswers,    \* page answers the person may record
    MaxProposals,  \* propose_requirements calls, which make something pending
    MaxAsks,       \* ask_to_confirm calls
    MaxMessages,   \* messages the person may send, which start turns
    MaxCrashes,
    MaxSwitches,   \* times the person may switch a conversation back to Plan
    MaxExtraHooks, \* extra on_recorded calls, as if record called it twice
    CutBetween     \* a crash may fall between store.confirmed and the append after it

VARIABLES
    \* On disk.
    ledger,     \* the project's answers: a sequence, TRUE when the answer confirms requirements
    pending,    \* items.pending of the project is not empty
    mode,       \* the conversation record's mode, "plan" or "design"
    wait,       \* waiting_on(transcript): -1 for None, else the pending result's answers_recorded
    told,       \* told_through(transcript)
    tail,       \* the transcript's last event is a DriverSaid with `answered`
    \* In memory, lost on a crash.
    running,    \* Channel.running
    turn,       \* where the conversation's running turn is
    seen,       \* answers_recorded as ask_to_confirm read it before the items
    rec,        \* the AskResult's answers_recorded
    asked,      \* the AskResult's status is pending
    cached,     \* the channel is in Channels, so `answered` reaches it
    callbacks,  \* done callbacks scheduled with call_soon and not run yet
    hooks,      \* on_recorded calls not run yet
    \* Ghosts.
    dels,       \* deliveries appended to the transcript
    on,         \* the delivery the running turn serves, 0 for a turn a message started
    served,     \* deliveries a turn has acted on
    dup,        \* a second turn acted on a delivery
    toldSet,    \* the answer numbers some event told the conversation
    twice,      \* an event told an answer the conversation was told before
    ended,      \* the told cursor of the step that last ended Plan
    \* Bounds.
    proposals, asks, messages, crashes, switches, extra

disk == <<ledger, pending, mode, wait, told, tail>>
memory == <<running, turn, seen, rec, asked, cached, callbacks, hooks>>
ghost == <<dels, on, served, dup, toldSet, twice, ended>>
bounds == <<proposals, asks, messages, crashes, switches, extra>>
vars == <<disk, memory, ghost, bounds>>

Turns == {"none", "fresh", "busy", "items", "after", "return"}
None == -1

Init ==
    /\ ledger = <<>>
    /\ pending = FALSE
    /\ mode = [c \in Convs |-> "plan"]
    /\ wait = [c \in Convs |-> None]
    /\ told = [c \in Convs |-> 0]
    /\ tail = [c \in Convs |-> FALSE]
    /\ running = [c \in Convs |-> FALSE]
    /\ turn = [c \in Convs |-> "none"]
    /\ seen = [c \in Convs |-> 0]
    /\ rec = [c \in Convs |-> 0]
    /\ asked = [c \in Convs |-> FALSE]
    /\ cached = [c \in Convs |-> FALSE]
    /\ callbacks = [c \in Convs |-> 0]
    /\ hooks = 0
    /\ dels = [c \in Convs |-> 0]
    /\ on = [c \in Convs |-> 0]
    /\ served = [c \in Convs |-> {}]
    /\ dup = FALSE
    /\ toldSet = [c \in Convs |-> {}]
    /\ twice = FALSE
    /\ ended = [c \in Convs |-> 0]
    /\ proposals = 0 /\ asks = 0 /\ messages = 0 /\ crashes = 0 /\ switches = 0 /\ extra = 0

Confirms(lo, hi) == \E i \in lo + 1..hi : ledger[i]

-----------------------------------------------------------------------------
(* Chat._deliver and the restart heal.                                     *)

\* _deliver's guards: not running, waiting_on is not None, and delivery() finds an answer past it.
CanDeliver(c) == ~running[c] /\ wait[c] # None /\ Len(ledger) > wait[c]

\* delivery().ends_plan: some answer in (waiting.through, through] confirms requirements.
EndsPlan(c) == mode[c] = "plan" /\ Confirms(wait[c], Len(ledger))

\* _deliver for every conversation in D at once: store.confirmed when ends_plan, then _begin,
\* which sets running, appends DriverSaid(answered=Answered(through=len(ledger))) and creates the
\* turn's task. One step: nothing else on the loop runs between them.
Deliver(D) ==
    LET L == Len(ledger) IN
    /\ mode' = [c \in Convs |-> IF c \in D /\ EndsPlan(c) THEN "design" ELSE mode[c]]
    /\ ended' = [c \in Convs |-> IF c \in D /\ EndsPlan(c) THEN L ELSE ended[c]]
    /\ twice' = (twice \/ \E c \in D : (wait[c] + 1..L) \cap toldSet[c] # {})
    /\ toldSet' = [c \in Convs |-> IF c \in D THEN toldSet[c] \cup (wait[c] + 1..L) ELSE toldSet[c]]
    /\ told' = [c \in Convs |-> IF c \in D THEN L ELSE told[c]]
    /\ wait' = [c \in Convs |-> IF c \in D THEN None ELSE wait[c]]
    /\ tail' = [c \in Convs |-> IF c \in D THEN TRUE ELSE tail[c]]
    /\ running' = [c \in Convs |-> IF c \in D THEN TRUE ELSE running[c]]
    /\ turn' = [c \in Convs |-> IF c \in D THEN "fresh" ELSE turn[c]]
    /\ dels' = [c \in Convs |-> IF c \in D THEN dels[c] + 1 ELSE dels[c]]
    /\ on' = [c \in Convs |-> IF c \in D THEN dels[c] + 1 ELSE on[c]]
    /\ UNCHANGED <<ledger, pending, seen, rec, asked, served, dup, bounds>>

\* The memory a crash loses: no turn runs, no channel is cached, no hook or callback is due.
Lost ==
    /\ running' = [c \in Convs |-> FALSE]
    /\ turn' = [c \in Convs |-> "none"]
    /\ seen' = [c \in Convs |-> 0]
    /\ rec' = [c \in Convs |-> 0]
    /\ asked' = [c \in Convs |-> FALSE]
    /\ cached' = [c \in Convs |-> FALSE]
    /\ callbacks' = [c \in Convs |-> 0]
    /\ hooks' = 0
    /\ on' = [c \in Convs |-> 0]
    /\ crashes' = crashes + 1

\* Chat.catch_up on stream open, which loads the channel into the cache. A crash between the
\* delivery's append and the turn's start leaves a DriverSaid tail: start the turn and append
\* nothing. Otherwise _deliver. The browser's EventSource opens the stream again by itself after
\* a restart, which is what makes this step fair.
CatchUp(c) ==
    /\ cached' = [cached EXCEPT ![c] = TRUE]
    /\ IF ~running[c] /\ tail[c] THEN
            /\ running' = [running EXCEPT ![c] = TRUE]
            /\ turn' = [turn EXCEPT ![c] = "fresh"]
            /\ on' = [on EXCEPT ![c] = dels[c]]
            /\ UNCHANGED <<disk, seen, rec, asked, callbacks, hooks, dels, served, dup, toldSet,
                           twice, ended, bounds>>
       ELSE IF CanDeliver(c) THEN
            /\ Deliver({c})
            /\ UNCHANGED <<callbacks, hooks>>
       ELSE
            /\ ~cached[c]
            /\ UNCHANGED <<disk, running, turn, seen, rec, asked, callbacks, hooks, ghost, bounds>>

\* Chat.answered from web.py record: _deliver on every cached channel of the account.
Hook ==
    /\ hooks > 0
    /\ hooks' = hooks - 1
    /\ Deliver({c \in Convs : cached[c] /\ CanDeliver(c)})
    /\ UNCHANGED <<cached, callbacks>>

\* The turn task's done callback, after run_turn's finally cleared running.
DoneCallback(c) ==
    /\ callbacks[c] > 0
    /\ callbacks' = [callbacks EXCEPT ![c] = @ - 1]
    /\ Deliver(IF CanDeliver(c) THEN {c} ELSE {})
    /\ UNCHANGED <<cached, hooks>>

\* A crash after store.confirmed and before the append that follows it in _deliver.
CutDeliver(c) ==
    /\ CutBetween
    /\ crashes < MaxCrashes
    /\ CanDeliver(c)
    /\ EndsPlan(c)
    /\ mode' = [mode EXCEPT ![c] = "design"]
    /\ ended' = [ended EXCEPT ![c] = Len(ledger)]
    /\ Lost
    /\ UNCHANGED <<ledger, pending, wait, told, tail, dels, served, dup, toldSet, twice,
                   proposals, asks, messages, switches, extra>>

-----------------------------------------------------------------------------
(* The person.                                                             *)

\* web.py record appends one answer to everything pending in the project, then calls
\* on_recorded on the loop. Answers.tla shows one recorded POST per answer.
Answer ==
    /\ pending
    /\ Len(ledger) < MaxAnswers
    /\ \E confirms \in BOOLEAN : ledger' = Append(ledger, confirms)
    /\ pending' = FALSE
    /\ hooks' = hooks + 1
    /\ UNCHANGED <<mode, wait, told, tail, running, turn, seen, rec, asked, cached, callbacks,
                   ghost, bounds>>

\* record calls on_recorded a second time for one answer, which the code does not do.
ExtraHook ==
    /\ extra < MaxExtraHooks
    /\ Len(ledger) > 0
    /\ extra' = extra + 1
    /\ hooks' = hooks + 1
    /\ UNCHANGED <<disk, running, turn, seen, rec, asked, cached, callbacks, ghost, proposals,
                   asks, messages, crashes, switches>>

\* Chat.start: refused while running, else UserSaid and a turn.
Start(c) ==
    /\ ~running[c]
    /\ messages < MaxMessages
    /\ messages' = messages + 1
    /\ running' = [running EXCEPT ![c] = TRUE]
    /\ turn' = [turn EXCEPT ![c] = "fresh"]
    /\ on' = [on EXCEPT ![c] = 0]
    /\ tail' = [tail EXCEPT ![c] = FALSE]
    /\ cached' = [cached EXCEPT ![c] = TRUE]
    /\ UNCHANGED <<ledger, pending, mode, wait, told, seen, rec, asked, callbacks, hooks, dels,
                   served, dup, toldSet, twice, ended, proposals, asks, crashes, switches, extra>>

\* The person picks Plan again after the conversation moved to Design.
SwitchToPlan(c) ==
    /\ mode[c] = "design"
    /\ switches < MaxSwitches
    /\ switches' = switches + 1
    /\ mode' = [mode EXCEPT ![c] = "plan"]
    /\ UNCHANGED <<ledger, pending, wait, told, tail, memory, ghost, proposals, asks, messages,
                   crashes, extra>>

\* The server process dies. The transcripts, the conversation records and the ledger stay.
Crash ==
    /\ crashes < MaxCrashes
    /\ Lost
    /\ UNCHANGED <<disk, dels, served, dup, toldSet, twice, ended, proposals, asks, messages,
                   switches, extra>>

-----------------------------------------------------------------------------
(* The running turn (chat/turn.py).                                        *)

Busy(c) == turn[c] = "busy"
Go(c, pc) == turn' = [turn EXCEPT ![c] = pc]

\* The turn's first append (AgentSaid, ToolCalled or TurnFailed) ends the DriverSaid tail.
TurnActs(c) ==
    /\ turn[c] = "fresh"
    /\ Go(c, "busy")
    /\ tail' = [tail EXCEPT ![c] = FALSE]
    /\ dup' = (dup \/ (on[c] # 0 /\ on[c] \in served[c]))
    /\ served' = IF on[c] # 0 THEN [served EXCEPT ![c] = @ \cup {on[c]}] ELSE served
    /\ UNCHANGED <<ledger, pending, mode, wait, told, running, seen, rec, asked, cached,
                   callbacks, hooks, dels, on, toldSet, twice, ended, bounds>>

\* propose_requirements: a new revision is pending in the project.
Propose(c) ==
    /\ Busy(c)
    /\ proposals < MaxProposals
    /\ proposals' = proposals + 1
    /\ pending' = TRUE
    /\ UNCHANGED <<ledger, mode, wait, told, tail, memory, ghost, asks, messages, crashes,
                   switches, extra>>

\* ask_to_confirm, after its wait: answers_recorded = len(ledger.answers), read before the items.
AskRead(c) ==
    /\ Busy(c)
    /\ asks < MaxAsks
    /\ asks' = asks + 1
    /\ Go(c, "items")
    /\ seen' = [seen EXCEPT ![c] = Len(ledger)]
    /\ UNCHANGED <<disk, running, rec, asked, cached, callbacks, hooks, ghost, proposals,
                   messages, crashes, switches, extra>>

\* ask_to_confirm reads the pending items. Pending: the result carries the count read before.
AskItems(c) ==
    /\ turn[c] = "items"
    /\ IF pending
         THEN /\ Go(c, "return")
              /\ asked' = [asked EXCEPT ![c] = TRUE]
              /\ rec' = [rec EXCEPT ![c] = seen[c]]
         ELSE /\ Go(c, "after")
              /\ UNCHANGED <<asked, rec>>
    /\ UNCHANGED <<disk, running, seen, cached, callbacks, hooks, ghost, bounds>>

\* Nothing pending: the result carries the ledger's length read again after the items.
AskAfter(c) ==
    /\ turn[c] = "after"
    /\ Go(c, "return")
    /\ asked' = [asked EXCEPT ![c] = FALSE]
    /\ rec' = [rec EXCEPT ![c] = Len(ledger)]
    /\ UNCHANGED <<disk, running, seen, cached, callbacks, hooks, ghost, bounds>>

\* answer_driver.settle, then the ToolReturned append, with no await between. settle moves the
\* cursor for every result, and calls store.confirmed only for a result that is not pending and
\* whose answers (told_through, answers_recorded] confirm requirements.
AskReturn(c) ==
    LET s == told[c]
        n == rec[c]
        new == s + 1..n
        ends == ~asked[c] /\ Confirms(s, n) /\ mode[c] = "plan"
    IN
    /\ turn[c] = "return"
    /\ mode' = [mode EXCEPT ![c] = IF ends THEN "design" ELSE @]
    /\ ended' = [ended EXCEPT ![c] = IF ends THEN n ELSE @]
    /\ twice' = (twice \/ new \cap toldSet[c] # {})
    /\ toldSet' = [toldSet EXCEPT ![c] = @ \cup new]
    /\ told' = [told EXCEPT ![c] = IF n > s THEN n ELSE s]
    /\ wait' = [wait EXCEPT ![c] = IF asked[c] THEN n ELSE None]
    /\ tail' = [tail EXCEPT ![c] = FALSE]
    /\ Go(c, "busy")
    /\ seen' = [seen EXCEPT ![c] = 0]
    /\ rec' = [rec EXCEPT ![c] = 0]
    /\ asked' = [asked EXCEPT ![c] = FALSE]
    /\ UNCHANGED <<ledger, pending, running, cached, callbacks, hooks, dels, on, served, dup,
                   bounds>>

\* A crash after settle's store.confirmed and before the ToolReturned append.
CutAsk(c) ==
    /\ CutBetween
    /\ crashes < MaxCrashes
    /\ turn[c] = "return"
    /\ ~asked[c] /\ Confirms(told[c], rec[c]) /\ mode[c] = "plan"
    /\ mode' = [mode EXCEPT ![c] = "design"]
    /\ ended' = [ended EXCEPT ![c] = rec[c]]
    /\ Lost
    /\ UNCHANGED <<ledger, pending, wait, told, tail, dels, served, dup, toldSet, twice,
                   proposals, asks, messages, switches, extra>>

\* run_turn returns; its finally clears running, and the loop schedules the done callback.
TurnEnd(c) ==
    /\ Busy(c)
    /\ Go(c, "none")
    /\ running' = [running EXCEPT ![c] = FALSE]
    /\ on' = [on EXCEPT ![c] = 0]
    /\ callbacks' = [callbacks EXCEPT ![c] = @ + 1]
    /\ UNCHANGED <<disk, seen, rec, asked, cached, hooks, dels, served, dup, toldSet, twice,
                   ended, bounds>>

-----------------------------------------------------------------------------

\* Nothing is left to do: no turn runs and no hook or callback is due.
Finished ==
    /\ \A c \in Convs : turn[c] = "none" /\ callbacks[c] = 0
    /\ hooks = 0
    /\ UNCHANGED vars

Next ==
    \/ Answer \/ ExtraHook \/ Hook \/ Crash \/ Finished
    \/ \E c \in Convs :
        \/ CatchUp(c) \/ DoneCallback(c) \/ CutDeliver(c)
        \/ Start(c) \/ SwitchToPlan(c)
        \/ TurnActs(c) \/ Propose(c) \/ AskRead(c) \/ AskItems(c) \/ AskAfter(c)
        \/ AskReturn(c) \/ CutAsk(c) \/ TurnEnd(c)

Spec == Init /\ [][Next]_vars

\* The loop runs what is due; the person's page reopens its stream. The person and the agent's
\* choices (answer, message, propose, ask) are not fair.
Fairness ==
    /\ WF_vars(Hook)
    /\ \A c \in Convs :
        /\ WF_vars(CatchUp(c)) /\ WF_vars(DoneCallback(c))
        /\ WF_vars(TurnActs(c)) /\ WF_vars(AskItems(c)) /\ WF_vars(AskAfter(c))
        /\ WF_vars(AskReturn(c)) /\ WF_vars(TurnEnd(c))

LiveSpec == Spec /\ Fairness

\* The conversations are interchangeable: no property names one.
Conversations == Permutations(Convs)

-----------------------------------------------------------------------------
(* Properties.                                                             *)

TypeOK ==
    /\ ledger \in Seq(BOOLEAN) /\ Len(ledger) <= MaxAnswers
    /\ pending \in BOOLEAN
    /\ mode \in [Convs -> {"plan", "design"}]
    /\ wait \in [Convs -> {None} \cup 0..MaxAnswers]
    /\ told \in [Convs -> 0..MaxAnswers]
    /\ tail \in [Convs -> BOOLEAN]
    /\ running \in [Convs -> BOOLEAN]
    /\ turn \in [Convs -> Turns]
    /\ seen \in [Convs -> 0..MaxAnswers] /\ rec \in [Convs -> 0..MaxAnswers]
    /\ asked \in [Convs -> BOOLEAN]
    /\ cached \in [Convs -> BOOLEAN]
    /\ callbacks \in [Convs -> Nat] /\ hooks \in Nat
    /\ dels \in [Convs -> Nat] /\ on \in [Convs -> Nat] /\ served \in [Convs -> SUBSET Nat]
    /\ dup \in BOOLEAN /\ twice \in BOOLEAN
    /\ toldSet \in [Convs -> SUBSET (1..MaxAnswers)]
    /\ ended \in [Convs -> 0..MaxAnswers]

\* No two turns act on one delivery: not a double POST, a restart or an answer during a turn.
\* The heal may start a turn again for a delivery whose turn a crash cut before it appended
\* anything; that turn did nothing, so it does not count.
OneTurnPerDelivery == ~dup

\* No transcript event tells the conversation an answer an earlier event told it.
NoAnswerToldTwice == ~twice

\* A delivery is never appended to a transcript while a turn runs in it.
NoDeliveryWhileRunning == [][\A c \in Convs : dels'[c] > dels[c] => ~running[c]]_vars

\* Plan ends only in a step that moves the told cursor over an answer that confirms
\* requirements, so a person who picks Plan again stays in Plan until they confirm again.
PlanEndsOnlyOnAnEdge ==
    [][\A c \in Convs :
        mode[c] = "plan" /\ mode'[c] = "design" =>
            told'[c] > told[c] /\ Confirms(told[c], told'[c])]_vars

\* A pending ask_to_confirm result never ends Plan, even when its answers_recorded moves the
\* cursor over an older confirming answer.
PendingAskKeepsPlan ==
    [][\A c \in Convs :
        turn[c] = "return" /\ asked[c] /\ mode[c] = "plan" => mode'[c] = "plan"]_vars

\* Each confirming answer ends Plan at most once for a conversation.
PlanEndsOncePerConfirm ==
    [][\A c \in Convs :
        mode[c] = "plan" /\ mode'[c] = "design" => Confirms(ended[c], ended'[c])]_vars

\* Every answer recorded while the conversation waits is told to it.
EveryAnswerTold ==
    \A c \in Convs, n \in 1..MaxAnswers :
        [](wait[c] # None /\ wait[c] < n /\ Len(ledger) >= n => <>(told[c] >= n))

\* Every delivery gets a turn that acts on it.
EveryDeliveryRuns == \A c \in Convs : [](tail[c] => <>~tail[c])
=============================================================================
