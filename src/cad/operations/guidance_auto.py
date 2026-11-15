"""What the agent is told about an Auto run, apart from guidance.py to keep each file small."""

from typing import Final

AUTO_DESCRIBED: Final = (
    "A requirement on a described load case counts in an Auto run like any confirmed one. The "
    "stop's all_pass lists those requirements apart as described. Report such a pass as a "
    "pass on a load case you described, not reviewed by our team."
)

AUTO_BUILDS: Final = (
    "Every build under an Auto run counts among the run's builds, once for each code and its "
    "parts, whether "
    "build_variant or auto_revise made it, in a new slot or an old one, and whether or not it "
    "built. The run's builds lists each one's code sha256, and the stop's report counts them. "
    "history holds only what auto_revise recorded."
)

AUTO_AGENT_CHECKS: Final = (
    "A requirement an approved agent-written check decides counts in an Auto run, so the run "
    "may start on it. A check the person declined or has not approved decides nothing and does "
    "not count. A pass on it is the mark pass_agent_check, and the stop's all_pass lists those "
    "requirements apart as agent_checked. Report such a pass as a pass of an agent-written "
    "check the person approved, not reviewed by our team, and never as a reviewed verdict, a "
    "reviewed check or a plain pass. A fail on it is a fail like any other, so revise against "
    "it. The check is frozen, so only the design can move."
)

AUTO_NEW_BODY_MATERIAL: Final = (
    "No confirmed made_of names a material for a body this code built, and neither do the "
    "materials auto_start was given, if any. A run records only those. Inside this run, revise a "
    "slot that already "
    "holds these bodies by passing its slot, or build code whose every body a confirmed made_of "
    "names. To add a body of a material no made_of names, call auto_ask to say so. The person's "
    "reply lets you start a new run with materials for each such body."
)

AUTO_ASK: Final = (
    "Stop an Auto run because you need the person: you are stuck, or only the person can "
    "decide, such as which of two conflicting requirements to relax. note says what you tried "
    "and what the person must decide, and names each requirement it is about. The stop's "
    "report gives the note as you wrote it. Returns the stopped run. The stop holds the "
    "conversation until the person writes or answers. On a run that has already stopped, "
    "nothing is recorded and the call is refused."
)

AUTO_STOP: Final = (
    "Stop an Auto run for the person, who pressed Stop in the web app. When the run is its "
    "conversation's current run, the stop holds the conversation, as every stop does: the "
    "agent cannot build, score or start a run in it until the person writes or answers. On a "
    "run that has already stopped, nothing more is recorded. Returns the stopped run and the "
    "conversation's running run and stopped run."
)
