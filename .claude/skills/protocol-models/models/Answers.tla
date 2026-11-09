------------------------------ MODULE Answers ------------------------------
(***************************************************************************)
(* The confirmation answer flow for one project with one brief:            *)
(* src/cad/confirmations/ballot.py (Desk), http.py (do_POST), page.py      *)
(* (answer_page), answers.py (append_answer) and records/signed.py         *)
(* (append, publish). Each server process has its own Desk, so two         *)
(* sessions can each open a page for the same item. The answers directory  *)
(* is shared and append-only: slot n is taken with os.link, which fails    *)
(* when another writer already holds it.                                   *)
(*                                                                         *)
(* An item is a revision of the brief's proposal (ItemRef.sha256). The     *)
(* agent can propose a new revision at any time; only the page appends.    *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
    Servers,      \* server processes, each with its own Desk and page server
    MaxRevisions, \* how many proposals the agent may make
    MaxPages,     \* how many ballots (tokens) may be opened in all
    MaxPosts,     \* how many POSTs the person's browser may send in all
    MaxFaults,    \* how many appends may fail with a store error
    Attempts      \* signed.ATTEMPTS

VARIABLES
    newest,     \* the latest proposal revision of the brief
    ledger,     \* answers/<n>.signed: a sequence of [rev, page]
    ballot,     \* Desk._ballots[project] per server: [page, rev, state]
    pages,      \* the pages the person opened with a GET: page -> [server, rev]
    posts,      \* each POST request so far: a sequence of request records
    faults,
    stale       \* ghost: an answer was linked for a revision the agent replaced after
                \* answer_page's pending check had passed

vars == <<newest, ledger, ballot, pages, posts, faults, stale>>

NoBallot == [page |-> 0, rev |-> 0, state |-> "none"]

Init ==
    /\ newest = 1
    /\ ledger = <<>>
    /\ ballot = [s \in Servers |-> NoBallot]
    /\ pages = <<>>
    /\ posts = <<>>
    /\ faults = 0
    /\ stale = FALSE

Answered(r) == \E i \in 1..Len(ledger) : ledger[i].rev = r

\* items.pending: the newest proposal while it is still PROPOSED, that is, unanswered.
Pending == IF Answered(newest) THEN {} ELSE {newest}

-----------------------------------------------------------------------------
(* The agent.                                                              *)

\* propose_requirements: a new revision, which makes the page's item stale.
Propose ==
    /\ newest < MaxRevisions
    /\ newest' = newest + 1
    /\ UNCHANGED <<ledger, ballot, pages, posts, faults, stale>>

\* ask_to_confirm -> Desk._open: keep the open ballot for the same items, else retire it and
\* open a new one with a new token. The person's browser then GETs the page (do_GET + view).
Ask(s) ==
    /\ Pending # {}
    /\ IF ballot[s].state = "open" /\ ballot[s].rev = newest
         THEN UNCHANGED <<ballot, pages>>
         ELSE /\ Len(pages) < MaxPages
              /\ ballot' = [ballot EXCEPT ![s] =
                                [page |-> Len(pages) + 1, rev |-> newest, state |-> "open"]]
              /\ pages' = Append(pages, [server |-> s, rev |-> newest])
    /\ UNCHANGED <<newest, ledger, posts, faults, stale>>

-----------------------------------------------------------------------------
(* The person's browser and do_POST.                                       *)

Post(g) ==
    /\ Len(posts) < MaxPosts
    /\ posts' = Append(posts, [page |-> g, server |-> pages[g].server, rev |-> pages[g].rev,
                               pc |-> "find", seen |-> 0, tries |-> 0, told |-> "nothing",
                               at |-> 0])
    /\ UNCHANGED <<newest, ledger, ballot, pages, faults, stale>>

Live(q) == ballot[q.server].page = q.page /\ ballot[q.server].state = "open"

Tell(k, q, what) == posts' = [posts EXCEPT ![k] = [q EXCEPT !.pc = "done", !.told = what]]
Go(k, q, pc) == posts' = [posts EXCEPT ![k] = [q EXCEPT !.pc = pc]]

\* do_POST: self._desk.find(token), with its own lock.
Find(k) ==
    LET q == posts[k] IN
    /\ q.pc = "find"
    /\ IF Live(q) THEN Go(k, q, "spend") ELSE Tell(k, q, "forbidden")
    /\ UNCHANGED <<newest, ledger, ballot, pages, faults, stale>>

\* do_POST: `self._desk.spend(token) is not ballot`. Of two concurrent POSTs, one spends it.
Spend(k) ==
    LET q == posts[k] IN
    /\ q.pc = "spend"
    /\ IF Live(q)
         THEN /\ ballot' = [ballot EXCEPT ![q.server].state = "spent"]
              /\ Go(k, q, "ledger")
         ELSE /\ Tell(k, q, "forbidden")
              /\ UNCHANGED ballot
    /\ UNCHANGED <<newest, ledger, pages, faults, stale>>

\* answer_page: read_ledger, then `any(ledger.of(ref) ...)`.
CheckLedger(k) ==
    LET q == posts[k] IN
    /\ q.pc = "ledger"
    /\ IF Answered(q.rev) THEN Tell(k, q, "already answered") ELSE Go(k, q, "pending")
    /\ UNCHANGED <<newest, ledger, ballot, pages, faults, stale>>

\* answer_page: `pending(kinds, ballot.project) != ballot.items`. The ghost field `at` keeps the
\* newest revision as this check saw it.
CheckPending(k) ==
    LET q == [posts[k] EXCEPT !.at = newest] IN
    /\ posts[k].pc = "pending"
    /\ IF Pending = {q.rev} THEN Go(k, q, "read") ELSE Tell(k, q, "changed")
    /\ UNCHANGED <<newest, ledger, ballot, pages, faults, stale>>

\* signed.append: read_numbered, then append_answer's record_for, which returns None when a
\* stored answer lists one of this page's items.
ReadSlots(k) ==
    LET q == posts[k] IN
    /\ q.pc = "read"
    /\ IF Answered(q.rev)
         THEN Tell(k, q, "already answered")
         ELSE posts' = [posts EXCEPT ![k] = [q EXCEPT !.pc = "publish", !.seen = Len(ledger)]]
    /\ UNCHANGED <<newest, ledger, ballot, pages, faults, stale>>

\* signed.publish: os.link to slot seen + 1. FileExistsError means another writer won the
\* slot, and append reads again, up to Attempts times, then raises Contended. A store error
\* (StoreUnusable, ProjectBusy) makes do_POST give the ballot back: Desk.give_back.
GiveBack(k, q) ==
    /\ ballot' = IF ballot[q.server].page = q.page /\ ballot[q.server].state = "spent"
                   THEN [ballot EXCEPT ![q.server].state = "open"] ELSE ballot
    /\ Tell(k, q, "not recorded")
    /\ UNCHANGED <<ledger, stale>>

Publish(k) ==
    LET q == posts[k] IN
    /\ q.pc = "publish"
    /\ \/ /\ Len(ledger) = q.seen
          /\ ledger' = Append(ledger, [rev |-> q.rev, page |-> q.page])
          /\ stale' = (stale \/ (q.at = q.rev /\ q.rev # newest))
          /\ Tell(k, q, "recorded")
          /\ UNCHANGED <<ballot, faults>>
       \/ /\ Len(ledger) # q.seen
          /\ q.tries + 1 < Attempts
          /\ posts' = [posts EXCEPT ![k] = [q EXCEPT !.pc = "read", !.tries = @ + 1]]
          /\ UNCHANGED <<ledger, ballot, faults, stale>>
       \/ /\ Len(ledger) # q.seen
          /\ q.tries + 1 >= Attempts
          /\ GiveBack(k, q)
          /\ UNCHANGED faults
       \/ /\ faults < MaxFaults
          /\ faults' = faults + 1
          /\ GiveBack(k, q)
    /\ UNCHANGED <<newest, pages>>

Request(k) == Find(k) \/ Spend(k) \/ CheckLedger(k) \/ CheckPending(k) \/ ReadSlots(k)
              \/ Publish(k)

\* Nothing is left to do: no step changes the state from here.
Finished ==
    /\ \A k \in 1..Len(posts) : posts[k].pc = "done"
    /\ UNCHANGED vars

Next ==
    \/ Propose
    \/ \E s \in Servers : Ask(s)
    \/ \E g \in 1..Len(pages) : Post(g)
    \/ \E k \in 1..Len(posts) : Request(k)
    \/ Finished

Spec == Init /\ [][Next]_vars

-----------------------------------------------------------------------------
(* Properties.                                                             *)

\* One signed answer per item: no two stored answers list the same revision.
OneAnswerPerItem ==
    \A i, j \in 1..Len(ledger) : i # j => ledger[i].rev # ledger[j].rev

\* One signed answer per page: a replayed or concurrent POST on a page writes nothing more.
OneAnswerPerPage ==
    \A i, j \in 1..Len(ledger) : i # j => ledger[i].page # ledger[j].page

\* Every POST the page told "Recorded" has its answer in the ledger.
RecordedIsKept ==
    \A k \in 1..Len(posts) :
        posts[k].told = "recorded" => \E i \in 1..Len(ledger) : ledger[i].page = posts[k].page

\* Every stored answer is for the revision the page showed.
AnswersWhatThePageShowed ==
    \A i \in 1..Len(ledger) : ledger[i].rev = pages[ledger[i].page].rev

\* A POST whose item the agent had replaced when answer_page checked what is pending records
\* nothing: the page says Changed.
ChangedWritesNothing ==
    \A k \in 1..Len(posts) : posts[k].told = "recorded" => posts[k].at = posts[k].rev

\* Desk.spend lets one request per page into answer_page at a time. A second POST of the page,
\* a double click or a replay, is refused until the first gives the ballot back.
InAnswerPage(k) == posts[k].pc \in {"ledger", "pending", "read", "publish"}
OneRequestPerPage ==
    \A i, j \in 1..Len(posts) :
        i # j /\ posts[i].page = posts[j].page => ~(InAnswerPage(i) /\ InAnswerPage(j))

\* A POST whose item the agent replaced after answer_page's pending check passed, and before the
\* answer was linked into place, writes nothing. The known finding: it does write.
StaleWritesNothing == ~stale
=============================================================================
