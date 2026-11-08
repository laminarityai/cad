# The agent's own measurements are information, never a verdict

Status: Accepted. The operator approved this ADR on 2026-11-08.

Many novice briefs ask for things that no team check measures, such as walls of at least 2 mm, a hole that fits an M5 bolt, or a snap-fit that does not break (#49). SPEC lets the agent write a check for such a requirement. The check passes automatic gates, and then the person reviews it. In review, a design that let the agent's geometry code grade designs broke three ways. It reported a 1.2 mm wall as 2.25 mm, a 0.4 mm floor as 8 mm and a 4.2 mm hole as 9 mm. Each time it passed every gate, and the person saw the same page for the honest check and the cheating one. This ADR records what phase 2 builds instead.

In this version, nothing the agent writes decides a requirement. Pass and fail come only from team checks. The one new graded kind is `measure_limit`. It holds a team check's measure to a limit that the person confirms. It may use only measures in a team catalogue, and each of those measures has the same value however the part is placed or turned.

The agent may send its own measuring code with a score. That code runs only in the build sandbox, in its own container, after the team checks. It measures the stored shape that the checks measured. Its numbers go on the scorecard in a separate `not_verified` list, and each is labelled "agent's own measurement, not verified". A number in that list has no verdict, no limit and no comparison. The requirement it relates to stays unverified. No requirement kind, formula or other graded path may read it, because that would turn the agent's number into a verdict. The server tells the agent to report each one as its own measurement, not verified, and never as a pass or a fail. Nothing is sent to the team, and there is no review queue.

The tracer counts each agent measurement as `NotVerified`, on its own line, and never as resolved. Its requirement still counts as not covered in both tracking numbers. Agent measurements do not block the phase 2 exit. The exit requires every number outside the `not_verified` list to trace to a confirmed source.

## Considered options

- **Agent-written geometry checks, gated and reviewed.** Rejected on 2026-11-08 after the adversarial review. Gates on reference shapes cannot tell an honest check from one written to flatter the agent's designs. A person who does not read code cannot tell them apart either.
- **Formulas over trusted measures, reviewed for each project.** Deferred, not rejected. A formula can reach only the measures it may read, and today that is volume alone. Formulas return when a count of unchecked requirements in the eval briefs shows the demand, and the team measures they need exist. A formula may never read an agent measurement.
- **A team review queue for agent code.** Rejected by the operator. No agent code is sent to the team for review.
- **No agent measurement at all.** Rejected. The agent can tell the user something useful about an unchecked requirement, as long as it never reads as checked.
- **An agent measurement blocks the phase 2 exit.** Rejected. Eval runs would then push the agent never to give the user its own measurement, which is the opposite of what it is for. Counting each one keeps it visible in the numbers.

## Consequences

ADR-0007 holds unamended. Its rule is that the graded party never chooses where a measurement happens. The agent's code does choose where it measures, but it grades nothing, so the rule still holds. ADR-0004 also holds unamended, because no new kind of item joins the confirmation page.

SPEC's agent-written check, with its gates and review for each project, is not built in this version. SPEC and GLOSSARY get a note, and GLOSSARY adds *agent measurement*. SPEC's exit sentence, "every number on every scorecard traces", gains one stated exception for the `not_verified` list.

Walls, holes and snap-fits are graded only once the team writes a measure for them. These are phase 3's `min_wall`, the hole measure of #100, and later a measure for snap-fit arms. Until then the counted reach of `measure_limit` is one measure.

The scorecard types for agent measurements sit in a file that every check version hashes, so adding them moves every team check version once. The code that runs the agent's measurements stays outside that set, and a test keeps it out.

A user may still read an unverified number as a check. The label, the server's instructions and the unverified requirement beside it are the defence.
