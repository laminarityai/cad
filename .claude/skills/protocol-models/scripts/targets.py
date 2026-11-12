"""What `check_models.py` runs: each TLC check and each mutant it must catch."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    module: str
    config: str
    finding: str | None = None
    """The violation this check is known to find, named as TLC names it, or None to pass."""


JOB_LANES: Final = Check("JobLanes", "JobLanes.tla", "JobLanes.cfg")
JOB_LANES_CAP: Final = Check("JobLanesCap", "JobLanes.tla", "JobLanesCap.cfg")
ANSWERS: Final = Check("Answers", "Answers.tla", "Answers.cfg")
CARRY_ON: Final = Check("CarryOn", "CarryOn.tla", "CarryOn.cfg")
CARRY_ON_LIVE: Final = Check("CarryOnLive", "CarryOn.tla", "CarryOnLive.cfg")
CHECKS: Final = (
    JOB_LANES,
    JOB_LANES_CAP,
    Check("JobLanesTwoServers", "JobLanes.tla", "JobLanesTwoServers.cfg"),
    Check(
        "JobLanesTwoServersRefusal",
        "JobLanes.tla",
        "JobLanesTwoServersRefusal.cfg",
        finding="InterruptedMeansInterrupted",
    ),
    Check("JobLanesPeek", "JobLanes.tla", "JobLanesPeek.cfg", finding="PeekMeansInterrupted"),
    ANSWERS,
    Check("AnswersStale", "Answers.tla", "AnswersStale.cfg", finding="StaleWritesNothing"),
    CARRY_ON,
    CARRY_ON_LIVE,
)


@dataclass(frozen=True, slots=True)
class Mutant:
    name: str
    regression: str
    check: Check
    edits: tuple[tuple[str, str], ...]
    """(old, new) text replacements; each old text must occur exactly once in the model."""
    catches: str


MUTANTS: Final = (
    Mutant(
        "quick-skips-flying",
        "_take_off stops looking in _flying",
        JOB_LANES,
        (('IF flying[p]["quick"] # "none" THEN', "IF FALSE THEN"),),
        "OneContainerPerKey",
    ),
    Mutant(
        "read-skips-mac",
        "job_store.read stops verifying the MAC",
        JOB_LANES,
        (('Stored(j) == disk[j] = "honest"', 'Stored(j) == disk[j] # "none"'),),
        "NeverTrustForged",
    ),
    Mutant(
        "attempt-kept-on-failure",
        "end_attempt runs only after a stored result, not in _attempt's finally",
        JOB_LANES_CAP,
        (
            (
                "/\\ attempt' = [attempt EXCEPT ![wjob[p]] = 0]",
                '/\\ attempt\' = IF wres[p] = "ok" THEN [attempt EXCEPT ![wjob[p]] = 0] '
                "ELSE attempt",
            ),
        ),
        "InterruptedMeansInterrupted",
    ),
    Mutant(
        "enqueue-starts-no-worker",
        "_take_off puts the job on the queue but never starts a worker for it",
        JOB_LANES_CAP,
        (
            (
                "IF ~worker[p]\n                 THEN /\\ worker'",
                "IF FALSE\n                 THEN /\\ worker'",
            ),
        ),
        "Temporal",
    ),
    Mutant(
        "drop-leaves-queue",
        "drop_unstarted gives the callers Superseded but leaves the job on the queue",
        JOB_LANES,
        (
            (
                "@ + 1]\n    /\\ queue' = [queue EXCEPT ![p] = <<>>]",
                "@ + 1]\n    /\\ queue' = queue",
            ),
        ),
        "QueuedIsCurrent",
    ),
    Mutant(
        "drop-keeps-flying",
        "drop_unstarted leaves the job in _flying, so a later settle waits on a Future nobody ends",
        JOB_LANES_CAP,
        (
            (
                'THEN /\\ flying\' = [flying EXCEPT ![p]["fea"] = "none"]',
                "THEN /\\ flying' = flying",
            ),
        ),
        "Temporal",
    ),
    Mutant(
        "notify-before-write",
        "_fly calls the listeners before job_store.write, so a snapshot then misses the result",
        JOB_LANES,
        (
            (
                '"writequick" ELSE "settlequick"]',
                '"notifyquick" ELSE "settlequick"]',
            ),
            (
                '"ok"]\n    /\\ cpc\' = [cpc EXCEPT ![t] = "land"]',
                '"ok"]\n    /\\ cpc\' = [cpc EXCEPT ![t] = "writequick"]',
            ),
            (
                'IF cres[t] \\in {"ok", "timeout"} THEN "notifyquick" ELSE "idle"]',
                'IF cres[t] \\in {"ok", "timeout"} THEN "land" ELSE "idle"]',
            ),
        ),
        "NotifiedAfterStore",
    ),
    Mutant(
        "no-cap-refusal",
        "_interrupted_too_often stops refusing fea at the attempt cap",
        JOB_LANES_CAP,
        (
            (
                'ELSE IF attempt["fea"] >= Cap THEN\n            /\\ cfea',
                "ELSE IF FALSE THEN\n            /\\ cfea",
            ),
        ),
        "CapStopsReruns",
    ),
    Mutant(
        "no-begin-attempt",
        "_attempt stops calling job_store.begin_attempt, so no crash is ever counted",
        JOB_LANES_CAP,
        (("/\\ attempt' = [attempt EXCEPT ![wjob[p]] = @ + 1]", "/\\ attempt' = attempt"),),
        "CapStopsReruns",
    ),
    Mutant(
        "dead-worker-kept",
        "_drain's finally leaves _worker set, the bug 0f22adb fixed",
        JOB_LANES_CAP,
        (("ELSE /\\ worker' = [worker EXCEPT ![p] = FALSE]", "ELSE /\\ worker' = worker"),),
        "Temporal",
    ),
    Mutant(
        "record-for-ignores-ledger",
        "append_answer's record_for stops refusing an item a stored answer lists",
        ANSWERS,
        (("/\\ IF Answered(q.rev)\n", "/\\ IF FALSE\n"),),
        "OneAnswerPerItem",
    ),
    Mutant(
        "publish-replaces",
        "signed.publish uses os.replace instead of os.link, so it overwrites a taken slot",
        ANSWERS,
        (
            ("/\\ Len(ledger) = q.seen\n", "/\\ Len(ledger) >= q.seen\n"),
            (
                "ledger' = Append(ledger, [rev |-> q.rev, page |-> q.page, by |-> q.by])",
                "ledger' = SubSeq(ledger, 1, q.seen)"
                " \\o <<[rev |-> q.rev, page |-> q.page, by |-> q.by]>>"
                " \\o SubSeq(ledger, q.seen + 2, Len(ledger))",
            ),
        ),
        "RecordedIsKept",
    ),
    Mutant(
        "no-changed-check",
        "answer_page stops returning Changed when the pending items no longer match the page",
        ANSWERS,
        (("IF Pending = {q.rev} THEN", "IF TRUE THEN"),),
        "ChangedWritesNothing",
    ),
    Mutant(
        "agent-answers",
        "verifier.person accepts an agent's access token, so the agent opens and posts the page",
        ANSWERS,
        (("Callers == Persons \\cup Others", "Callers == Persons \\cup Others \\cup Agents"),),
        "OnlyTenantPersonsAnswer",
    ),
    Mutant(
        "seal-ignores-session",
        "snapshot.seal stops binding the session, so another session's leaked form records",
        ANSWERS,
        (("/\\ q.by = pages[q.page].person\n", "/\\ TRUE\n"),),
        "AnsweredByTheOpener",
    ),
    Mutant(
        "snapshot-unbound",
        "answer_page drops its account check and the seal stops binding the session, so a form"
        " that leaked to another account records",
        ANSWERS,
        (
            (
                "IF /\\ Account(q.by) = Tenant\n          /\\ q.by = pages[q.page].person\n",
                "IF TRUE\n",
            ),
            # Another session of the tenant's account could also post the leaked form, which
            # breaks AnsweredByTheOpener at the same depth; masking it keeps the verdict stable.
            (
                "    \\A i \\in 1..Len(ledger) : ledger[i].by = pages[ledger[i].page].person\n",
                "    TRUE\n",
            ),
        ),
        "OnlyTenantPersonsAnswer",
    ),
    Mutant(
        "deliver-ignores-running",
        "_deliver stops returning while a turn runs, so an answer that lands mid-turn starts a"
        " second turn beside it",
        CARRY_ON,
        (("CanDeliver(c) == ~running[c] /\\ ", "CanDeliver(c) == "),),
        "NoDeliveryWhileRunning",
    ),
    Mutant(
        "delivery-keeps-waiting",
        "waiting_on stops treating a delivery as the end of the wait, so the done callback"
        " delivers the same answers again",
        CARRY_ON,
        (
            (
                "wait' = [c \\in Convs |-> IF c \\in D THEN None ELSE wait[c]]",
                "wait' = wait",
            ),
        ),
        "NoAnswerToldTwice",
    ),
    Mutant(
        "heal-after-act",
        "catch_up restarts a turn when the transcript holds any delivery, not only a DriverSaid"
        " tail, so a reopened stream runs a delivery's turn again",
        CARRY_ON,
        (("IF ~running[c] /\\ tail[c] THEN", "IF ~running[c] /\\ dels[c] > 0 THEN"),),
        "OneTurnPerDelivery",
    ),
    Mutant(
        "no-restart-heal",
        "catch_up drops the restart heal, so a crash between a delivery and its turn leaves the"
        " conversation silent",
        CARRY_ON_LIVE,
        (("IF ~running[c] /\\ tail[c] THEN", "IF FALSE THEN"),),
        "Temporal",
    ),
    Mutant(
        "answered-count-before-items",
        "ask_to_confirm reads answers_recorded only before the items, so an answer that lands"
        " between the two reads returns answered, ends the wait and is never told",
        CARRY_ON_LIVE,
        (("rec' = [rec EXCEPT ![c] = Len(ledger)]", "rec' = [rec EXCEPT ![c] = seen[c]]"),),
        "Temporal",
    ),
)
