"""The code regressions the JobLanes model must catch."""

from typing import Final

from targets import JOB_LANES, JOB_LANES_CAP, JOB_LANES_STOP, Mutant

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
        JOB_LANES,
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
                "@ + 1]\n              /\\ queue' = [queue EXCEPT ![p] = <<>>]",
                "@ + 1]\n              /\\ queue' = queue",
            ),
        ),
        "QueuedIsCurrent",
    ),
    Mutant(
        "drop-shown-elsewhere",
        "build_into_set drops a replaced revision's queued jobs while another brief's set still"
        " shows the variant (#167)",
        JOB_LANES,
        (("    /\\ IF shown = 1\n", "    /\\ IF TRUE\n"),),
        "KeptWhileShown",
    ),
    Mutant(
        "drop-keeps-flying",
        "_refuse_locked leaves the job in _flying, so a later settle waits on a Future nobody ends",
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
        "peek-ignores-flying",
        "_look stops calling a job that runs here pending, so the scorecard refuses a healthy"
        " rerun as interrupted (#150)",
        JOB_LANES_CAP,
        (
            (
                'ELSE IF flying[p]["fea"] = "none" /\\ attempt["fea"] >= Cap',
                'ELSE IF attempt["fea"] >= Cap',
            ),
        ),
        "PeekMeansInterrupted",
    ),
    Mutant(
        "stop-counts",
        "Lanes.close leaves the running attempt counted, so each deploy during a check counts"
        " toward the cap and the scorecard refuses the check as interrupted (#106)",
        JOB_LANES_STOP,
        (
            (
                "/\\ attempt' = IF Counted(p) THEN [attempt EXCEPT ![wjob[p]] = IF @ > 0 THEN @ - 1"
                " ELSE 0]\n                  ELSE attempt",
                "/\\ attempt' = attempt",
            ),
        ),
        "PeekMeansInterrupted",
    ),
    Mutant(
        "end-after-close",
        "_attempt's finally calls end_attempt after Lanes.close took the attempt back, so the"
        " crashes counted before the stop are forgotten",
        JOB_LANES_STOP,
        (
            (
                "         ELSE UNCHANGED <<attempt, cut>>",
                "         ELSE /\\ attempt' = [attempt EXCEPT ![wjob[p]] = 0]\n"
                "              /\\ UNCHANGED cut",
            ),
        ),
        "CapStopsReruns",
    ),
    Mutant(
        "orphans-survive",
        "remove_orphans removes only exited containers, so a dead server's fea runs on beside"
        " its rerun (#148)",
        JOB_LANES,
        (("/\\ orphans' = [q \\in Procs |-> {}]", "/\\ orphans' = orphans"),),
        "OneContainerPerKey",
    ),
)
