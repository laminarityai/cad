# Agent-written checks are frozen, gated and approved for one project

Status: Accepted. The operator made every decision below on 2026-11-11. This ADR records them and supersedes ADR-0008. None of it is built yet.

Most requirements a novice writes have no check, so most scorecards say "not checked" (#49). On the brief-set run of 2026-11-08, reviewed checks covered 56 of 103 requirements. ADR-0008 ruled that nothing the agent writes decides a requirement, because gates on reference shapes could not tell an honest geometry check from one written to flatter the agent's designs. On 2026-11-11 the operator reversed that ruling: agent-written checks get built, gated, and reviewed for each project by the person, labelled and counted apart. This ADR records how. ADR-0008's finding still stands. No gate tells an honest geometry measure from a flattering one, and this design does not claim to.

## The decision

The agent may write a check for a requirement that no team check decides. It calls `write_check` after it proposes the requirement and before any variant of the brief exists. Once a brief has built variants, the agent may not write a check for it. This is the blind rule.

A check is a signed record in its project. It holds:

- plain words for what it measures;
- optional build123d measuring code, which runs only in the sandbox and receives only the stored shape;
- one formula in a small closed arithmetic grammar, which team code parses and evaluates on the host, so no agent Python runs there;
- the inputs the formula reads, each bound to exactly one of: a value its own measuring code reports, a team measure by exact key, a table or researched value, or a constant written in its cited source;
- a limit, which is the person's confirmed number or a constant from the source;
- one worked example from a cited page.

The server freezes the check by its hash only when every gate passes:

- **Blind.** No variant of the brief exists.
- **Form.** Sizes, units, the grammar, and every binding exist. The formula or its limit reads at least one value from the source, the tables or research. A check that is only a geometry measure, such as a wall thickness or a hole diameter, is refused. Those wait for team checks.
- **Units.** The formula's units agree.
- **Worked example.** The server fetches the page under ADR-0009's fetching rules, finds the quote and every number in it with ADR-0009's two checks, and the formula gives the quoted result.
- **Repeat and turn.** The measuring code gives the same values in two containers, and when the part is turned by a rigid motion the agent cannot compute.

There is no edit. A changed check is a new record, needs a new review, and must pass the blind rule again.

The person approves the check on the confirmation page, as an item beside the requirement it decides, with the same single Confirm. Approval means "this tests what I meant". It does not mean the code or the source is right. Declining the check leaves the requirement unverified.

An approved check's verdict is labelled "agent-written check you approved, not reviewed by our team". Auto counts its pass toward every requirement passing and revises against its fail, and the stop report lists those passes apart, as it does for researched ones. An unapproved or declined check has no verdict, by type. Its numbers show as the agent's own measurement, not verified, as ADR-0008 ruled.

The tracer counts approved checks on their own line. They stay out of reviewed coverage and out of the strict pass rate, which count team checks only.

An agent measurement becomes an agent-written check with no limit. It runs through the same harness and never gets a verdict.

## Walls the person states

A wall thickness the person states is a design target, not printability, so SPEC's printability exclusion does not cover it. The `min_wall` team check decides it ([docs/design/min-wall.md](../design/min-wall.md)). It decides only a limit the person confirmed. It has no default derived from a printer and gives no universal verdict on walls nobody stated. Printability itself stays deferred.

## What still holds from ADR-0008

- An agent measurement that no person approved is information, never a verdict. It has no limit, no comparison and no verdict field.
- No formula of a team check reads an agent measurement.
- The agent's measuring code runs only in the sandbox, after the team checks, on the stored shape they measured.
- Nothing is sent to the team, and there is no review queue.

## Considered options

- **Keep ADR-0008.** Rejected by the operator on 2026-11-11, because coverage comes first.
- **Allow a check after the brief has variants.** Rejected by the operator. A check written after the designs exist can be tuned to them, and a check rewritten after a failure looks the same on the page.
- **Allow a check that is only a geometry measure.** Rejected by the operator. No worked example can test it, so the gates prove nothing about it. Walls and holes go to team checks.
- **Count approved checks in reviewed coverage.** Rejected by the operator. They get their own line, so the claim that team checks decide stays measurable.
- **Leave approved checks out of Auto.** Rejected by the operator. Auto counts their passes and revises on their fails, always labelled.
- **Give an unapproved check a labelled verdict.** Rejected. An unapproved result must never read like a verdict.
- **The formula as Python in the sandbox.** Rejected. The host could then not check its units or rerun the worked example without running agent code.

## Consequences

The agent now writes a grader. AGENTS.md's rule that the agent never decides whether a design is good gains a second exception beside research, with the same promise: labelled and counted apart.

ADR-0007 holds for team checks. An agent-written check does choose where it measures, which ADR-0007 exists to forbid. The blind rule, the turned run and the label are the defence, and they are weaker than ADR-0007.

ADR-0004 holds. A new item kind joins the confirmation page, as context parts did.

ADR-0010's rule that only `Checked` rows count toward every requirement passing gains the approved agent-written check, labelled in the stop report.

A new scorecard row type for an approved check's verdict joins the scorecard model, which every check version hashes. Every team check version moves once.

A requirement first stated after its brief has variants cannot get an agent-written check. It stays unverified until a team check decides it.

A person may still read an approved agent-written check as a team check. The label, the page's words and the separate count are the defence. The only real evidence of a check's honesty is agreement with a team check, so stored agent-written checks get rerun on the same variants against the holes check and `min_wall`.
