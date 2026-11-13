"""The code regressions the Answers, CarryOn and AutoHold models must catch."""

from typing import Final

from targets import ANSWERS, AUTO_HOLD, CARRY_ON, CARRY_ON_LIVE, Mutant

MUTANTS: Final = (
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
    Mutant(
        "stop-holds-nothing",
        "record_event moves a stopped run out of auto_run but no longer writes stopped_run, so"
        " the next build binds no run and passes",
        AUTO_HOLD,
        (("/\\ stopped' = [stopped EXCEPT ![c] = r]", "/\\ stopped' = stopped"),),
        "NoBuildPastAStop",
    ),
    Mutant(
        "bind-skips-the-stop",
        "bind passes only auto_run, so after a stop build_variant and score_variant run with no"
        " run, the gap before ADR-0010's 2026-11-11 amendment",
        AUTO_HOLD,
        (
            (
                "Bound(c) == IF auto[c] # 0 THEN auto[c] ELSE stopped[c]",
                "Bound(c) == auto[c]",
            ),
        ),
        "NoBuildPastAStop",
    ),
    Mutant(
        "gate-clears-the-hold",
        "the gate clears stopped_run when it refuses a build, so a tool call reopens Auto",
        AUTO_HOLD,
        (
            (
                "/\\ Record(r) \\* RunStopped",
                "/\\ stopped' = [stopped EXCEPT ![c] = 0]"
                " /\\ UNCHANGED <<runs, auto, acted, holdAt>>",
            ),
        ),
        "OnlyAPersonStepReopens",
    ),
    Mutant(
        "start-ignores-the-hold",
        "start_run drops its stopped_run refusal, so the agent starts a run after a stop",
        AUTO_HOLD,
        (
            (
                "IN IF s1 # 0 \\/ RunningRuns # {} \\/ Len(runs) = MaxRuns THEN",
                "IN IF RunningRuns # {} \\/ Len(runs) = MaxRuns THEN",
            ),
        ),
        "NoRunWithoutAPersonStep",
    ),
    Mutant(
        "start-beside-a-running-run",
        "open_under_lock creates a new run while the brief's run still runs",
        AUTO_HOLD,
        (
            (
                "IN IF s1 # 0 \\/ RunningRuns # {} \\/ Len(runs) = MaxRuns THEN",
                "IN IF s1 # 0 \\/ Len(runs) = MaxRuns THEN",
            ),
        ),
        "OneRunningRunPerConversation",
    ),
    Mutant(
        "start-ignores-pending",
        "auto_start drops its pending-proposal refusal",
        AUTO_HOLD,
        (("/\\ startAt' = IF Pending THEN refused ELSE next", "/\\ startAt' = next"),),
        "NoBuildUnderAPendingProposal",
    ),
    Mutant(
        "pending-before-watermark",
        "auto_start checks for a pending proposal before it reads the watermark, so a proposal"
        " that lands between the two is inside the watermark and never stops the run",
        AUTO_HOLD,
        (
            (
                'ReadOrder == <<"watermark", "pending", "confirmed">>',
                'ReadOrder == <<"pending", "watermark", "confirmed">>',
            ),
        ),
        "NoBuildUnderAPendingProposal",
    ),
    Mutant(
        "confirmed-before-pending",
        "auto_start reads the confirmed set before the pending check, so a proposal confirmed"
        " between the two changes the decision under the run",
        AUTO_HOLD,
        (
            (
                'ReadOrder == <<"watermark", "pending", "confirmed">>',
                'ReadOrder == <<"watermark", "confirmed", "pending">>',
            ),
        ),
        "BuiltUnderItsDecision",
    ),
    Mutant(
        "heal-lifts-the-hold",
        "catch_up's restart heal lifts the hold, so a Stop pressed after a delivery is cleared"
        " when the delivery's turn runs again",
        AUTO_HOLD,
        (
            (
                "/\\ on' = [on EXCEPT ![c] = tailAct[c]]\n"
                "    /\\ UNCHANGED <<auto, stopped, untouched>>",
                "/\\ on' = [on EXCEPT ![c] = tailAct[c]]\n    /\\ LiftHold(c)",
            ),
        ),
        "OnlyAPersonStepReopens",
    ),
    Mutant(
        "append-before-lift",
        "_begin appends the person's event before lift_hold, so a crash between them leaves a"
        " delivery whose rerun turn the old stop still holds",
        AUTO_HOLD,
        (
            ("First(c) == Lifted(c)", "First(c) == Appended(c)"),
            ("Second(c) == Appended(c)", "Second(c) == Lifted(c)"),
        ),
        "ActedLiftsTheHold",
    ),
    Mutant(
        "record-skips-the-heal",
        "record_event writes the hold only for the stop it records, so a stop that a crash cut"
        " before its conversation write stays unwritten after the next call",
        AUTO_HOLD,
        (("    ELSE /\\ HoldFor(r)", "    ELSE /\\ UNCHANGED <<auto, stopped>>"),),
        "HealedByTheNextCall",
    ),
)
