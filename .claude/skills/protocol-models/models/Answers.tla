------------------------------ MODULE Answers ------------------------------
(***************************************************************************)
(* The confirmation answer flow for one project with one brief, in the     *)
(* signed-in web app: src/cad/confirmations/web.py (show, record),         *)
(* operations/confirmation.py (answer_page), snapshot.py (seal, unseal),   *)
(* page.py (answer_page), answers.py (append_answer) and records/signed.py *)
(* (append, publish).                                                      *)
(*                                                                         *)
(* A GET mints a snapshot: the pending items, sealed with the projects key *)
(* over the account and the session that asked. Nothing about a page is    *)
(* kept in memory, so which server process a request reaches does not     *)
(* matter, and the model has no server. The answers directory is shared    *)
(* and append-only: slot n is taken with os.link, which fails when another *)
(* writer already holds it.                                                *)
(*                                                                         *)
(* An item is a revision of the brief's proposal (ItemRef.sha256). The     *)
(* agent can propose a new revision at any time; only a person's POST      *)
(* appends.                                                                *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
    Persons,      \* person sessions of the tenant's account
    Others,       \* person sessions of another account
    Agents,       \* agent principals of the tenant's account
    MaxRevisions, \* how many proposals the agent may make
    MaxPages,     \* how many distinct snapshots may be minted in all
    MaxPosts,     \* how many POSTs may be sent in all
    MaxFaults,    \* how many appends may fail with a store error
    Attempts      \* signed.ATTEMPTS

VARIABLES
    newest,     \* the latest proposal revision of the brief
    ledger,     \* answers/<n>.signed: a sequence of [rev, page, by]
    pages,      \* the snapshots minted by a GET: page -> [person, rev]
    posts,      \* each POST request so far: a sequence of request records
    faults,
    stale       \* ghost: an answer was linked for a revision the agent replaced after
                \* answer_page's pending check had passed

vars == <<newest, ledger, pages, posts, faults, stale>>

Tenant == "tenant"
Account(p) == IF p \in Others THEN "other" ELSE Tenant

\* The principals verifier.person accepts. An agent's access token is not a person session.
Callers == Persons \cup Others

Init ==
    /\ newest = 1
    /\ ledger = <<>>
    /\ pages = <<>>
    /\ posts = <<>>
    /\ faults = 0
    /\ stale = FALSE

Answered(r) == \E i \in 1..Len(ledger) : ledger[i].rev = r

\* items.pending: the newest proposal while it is still PROPOSED, that is, unanswered.
Pending == IF Answered(newest) THEN {} ELSE {newest}

-----------------------------------------------------------------------------
(* The agent.                                                              *)

\* propose_requirements: a new revision, which makes every minted snapshot stale.
Propose ==
    /\ newest < MaxRevisions
    /\ newest' = newest + 1
    /\ UNCHANGED <<ledger, pages, posts, faults, stale>>

-----------------------------------------------------------------------------
(* The browser, web.py and answer_page.                                    *)

\* web.py show: snapshot.seal over the caller's session and the pending items. The seal is an
\* HMAC, so the same session and items give the same snapshot again. Another account's person
\* reaches its own tenant, so it never mints a snapshot of this store.
Get(p) ==
    LET shown == [person |-> p, rev |-> newest] IN
    /\ Account(p) = Tenant
    /\ Pending # {}
    /\ shown \notin {pages[g] : g \in 1..Len(pages)}
    /\ Len(pages) < MaxPages
    /\ pages' = Append(pages, shown)
    /\ UNCHANGED <<newest, ledger, posts, faults, stale>>

\* web.py record: any caller may send any minted snapshot, its own or one that leaked, again
\* and again. Two POSTs of one form both run; nothing is spent.
Post(p, g) ==
    /\ Len(posts) < MaxPosts
    /\ posts' = Append(posts, [page |-> g, by |-> p, rev |-> pages[g].rev,
                               pc |-> "unseal", seen |-> 0, tries |-> 0, told |-> "nothing",
                               at |-> 0])
    /\ UNCHANGED <<newest, ledger, pages, faults, stale>>

Tell(k, q, what) == posts' = [posts EXCEPT ![k] = [q EXCEPT !.pc = "done", !.told = what]]
Go(k, q, pc) == posts' = [posts EXCEPT ![k] = [q EXCEPT !.pc = pc]]

\* operations/confirmation.answer_page: refuse when person.account != tenant.account, else
\* snapshot.unseal, which verifies the MAC over the caller's own account and session.
Unseal(k) ==
    LET q == posts[k] IN
    /\ q.pc = "unseal"
    /\ IF /\ Account(q.by) = Tenant
          /\ q.by = pages[q.page].person
         THEN Go(k, q, "ledger")
         ELSE Tell(k, q, "forbidden")
    /\ UNCHANGED <<newest, ledger, pages, faults, stale>>

\* page.answer_page: read_ledger, then `any(ledger.of(ref) ...)`.
CheckLedger(k) ==
    LET q == posts[k] IN
    /\ q.pc = "ledger"
    /\ IF Answered(q.rev) THEN Tell(k, q, "already answered") ELSE Go(k, q, "pending")
    /\ UNCHANGED <<newest, ledger, pages, faults, stale>>

\* page.answer_page: `pending(kinds, project) != items`. The ghost field `at` keeps the newest
\* revision as this check saw it.
CheckPending(k) ==
    LET q == [posts[k] EXCEPT !.at = newest] IN
    /\ posts[k].pc = "pending"
    /\ IF Pending = {q.rev} THEN Go(k, q, "read") ELSE Tell(k, q, "changed")
    /\ UNCHANGED <<newest, ledger, pages, faults, stale>>

\* signed.append: read_numbered, then append_answer's record_for, which returns None when a
\* stored answer lists one of this page's items; answer_page then says AlreadyAnswered.
ReadSlots(k) ==
    LET q == posts[k] IN
    /\ q.pc = "read"
    /\ IF Answered(q.rev)
         THEN Tell(k, q, "already answered")
         ELSE posts' = [posts EXCEPT ![k] = [q EXCEPT !.pc = "publish", !.seen = Len(ledger)]]
    /\ UNCHANGED <<newest, ledger, pages, faults, stale>>

\* signed.publish: os.link to slot seen + 1. FileExistsError means another writer won the
\* slot, and append reads again, up to Attempts times, then raises Contended (ProjectBusy). A
\* store error or ProjectBusy makes record answer 500: nothing recorded, send the form again.
Publish(k) ==
    LET q == posts[k] IN
    /\ q.pc = "publish"
    /\ \/ /\ Len(ledger) = q.seen
          /\ ledger' = Append(ledger, [rev |-> q.rev, page |-> q.page, by |-> q.by])
          /\ stale' = (stale \/ (q.at = q.rev /\ q.rev # newest))
          /\ Tell(k, q, "recorded")
          /\ UNCHANGED faults
       \/ /\ Len(ledger) # q.seen
          /\ q.tries + 1 < Attempts
          /\ posts' = [posts EXCEPT ![k] = [q EXCEPT !.pc = "read", !.tries = @ + 1]]
          /\ UNCHANGED <<ledger, faults, stale>>
       \/ /\ Len(ledger) # q.seen
          /\ q.tries + 1 >= Attempts
          /\ Tell(k, q, "not recorded")
          /\ UNCHANGED <<ledger, faults, stale>>
       \/ /\ faults < MaxFaults
          /\ faults' = faults + 1
          /\ Tell(k, q, "not recorded")
          /\ UNCHANGED <<ledger, stale>>
    /\ UNCHANGED <<newest, pages>>

Request(k) == Unseal(k) \/ CheckLedger(k) \/ CheckPending(k) \/ ReadSlots(k) \/ Publish(k)

\* Nothing is left to do: no step changes the state from here.
Finished ==
    /\ \A k \in 1..Len(posts) : posts[k].pc = "done"
    /\ UNCHANGED vars

Next ==
    \/ Propose
    \/ \E p \in Callers : Get(p)
    \/ \E p \in Callers, g \in 1..Len(pages) : Post(p, g)
    \/ \E k \in 1..Len(posts) : Request(k)
    \/ Finished

Spec == Init /\ [][Next]_vars

\* The tenant's sessions are interchangeable: no property names one.
Sessions == Permutations(Persons)

-----------------------------------------------------------------------------
(* Properties.                                                             *)

\* One signed answer per item: no two stored answers list the same revision.
OneAnswerPerItem ==
    \A i, j \in 1..Len(ledger) : i # j => ledger[i].rev # ledger[j].rev

\* One signed answer per snapshot: a replayed or concurrent POST of a form writes nothing more.
OneAnswerPerPage ==
    \A i, j \in 1..Len(ledger) : i # j => ledger[i].page # ledger[j].page

\* Every stored answer was given by a person session of the tenant's account: never an agent,
\* never another account.
OnlyTenantPersonsAnswer ==
    \A i \in 1..Len(ledger) : ledger[i].by \in Persons /\ Account(ledger[i].by) = Tenant

\* Every stored answer was given by the session the snapshot was sealed for, so a form that
\* leaked to another session of the account records nothing.
AnsweredByTheOpener ==
    \A i \in 1..Len(ledger) : ledger[i].by = pages[ledger[i].page].person

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

\* A POST whose item the agent replaced after answer_page's pending check passed, and before the
\* answer was linked into place, writes nothing. The known finding: it does write.
StaleWritesNothing == ~stale
=============================================================================
