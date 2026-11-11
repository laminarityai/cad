"""What the chat does for an Auto run, beyond what the agent does.

The server decides when a run stops and refuses every call after it (ADR-0010), so the driver
holds no rule of its own. It does two things the server cannot. It reads the run's signed log
and posts the stop's report once, whoever stopped it: the agent, a passing scorecard, the usage
cap, or the person's Stop, during a turn or between two. And it reminds an agent that ended its
message with the run still running to call `auto_revise` or `auto_ask`, a few times at most.

The driver follows only this conversation's runs: the one the conversation holds, or one an auto
tool returned to this conversation's agent. The server refuses a call on any other run, so a run
id the agent names in a refused call is never followed.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import ValidationError

from cad.auto import log
from cad.auto.model import AutoRun, Stopped, TamperedRun, UnknownRun
from cad.auto.step import report
from cad.briefs import store as briefs
from cad.briefs.store import BriefRefused
from cad.briefs.words import describe
from cad.chat.log import Event, StopReport, ToolCalled, ToolReturned, TurnFailed
from cad.chat.model import ToolResult, ToolUse
from cad.confirmations.requirements import plain_names
from cad.conversations import store
from cad.conversations.model import Mode
from cad.operations.model import Tenant
from cad.projects.model import ProjectRefused

AUTO_TOOLS: Final = frozenset({"auto_start", "auto_revise", "auto_ask"})
MAX_NUDGES: Final = 3
NUDGE: Final = (
    "Auto run {run_id} has not stopped. Call auto_revise with new build123d code for the "
    "failing requirements, or auto_ask with a note if you are stuck or the person must decide. "
    "Do not end your message while the run is running."
)


@dataclass
class AutoDriver:
    tenant: Tenant
    run_id: str | None
    reported: bool = False
    nudges: int = 0

    @staticmethod
    def resume(tenant: Tenant, events: Sequence[Event]) -> "AutoDriver":
        """Follow the run the conversation holds, or else the last run an auto tool returned in
        its transcript, because a stop clears the held run. The run counts as reported only when
        the transcript holds its report, so a stop no turn saw is reported by the next turn."""
        cid = tenant.conversation
        held = None if cid is None else store.read(tenant.conversations, cid).auto_run
        run_id = held or _last_run(events)
        reported = any(isinstance(one, StopReport) and one.run_id == run_id for one in events)
        return AutoDriver(tenant, run_id, reported)

    def observe(self, call: ToolUse, result: ToolResult) -> None:
        if call.name not in AUTO_TOOLS or result.is_error:
            return
        run_id = _run_of(result.text)
        if run_id is not None and run_id != self.run_id:
            self.run_id, self.reported, self.nudges = run_id, False, 0

    def ending(self) -> StopReport | TurnFailed | None:
        """A stop's report this conversation has not yet seen, read from the signed run log."""
        if self.reported:
            return None
        try:
            run = self._stopped()
        except TamperedRun as tampered:
            return TurnFailed(message=str(tampered))
        if run is None:
            return None
        self.reported = True
        assert isinstance(run.state, Stopped)
        state = run.state
        said = report(state.history, state.reason, self._statements(state.start.brief_id))
        return StopReport(run_id=run.run_id, reason=state.reason.kind, report=said)

    def nudge(self) -> str | None:
        if self.reported or self.run_id is None or self.nudges >= MAX_NUDGES:
            return None
        cid = self.tenant.conversation
        if cid is None or store.read(self.tenant.conversations, cid).mode is not Mode.AUTO:
            return None
        if self._stopped() is not None:
            return None
        self.nudges += 1
        return NUDGE.format(run_id=self.run_id)

    def _statements(self, brief_id: str) -> dict[str, str]:
        """Each requirement the brief ever proposed, by id, in the words the person read."""
        roots = self.tenant.roots
        try:
            proposals = briefs.read_state(roots, brief_id).proposals
            names = plain_names(roots, brief_id)
        except (BriefRefused, ProjectRefused):
            return {}
        return {r.id: describe(r, names) for one in proposals for r in one.requirements}

    def _stopped(self) -> AutoRun | None:
        if self.run_id is None:
            return None
        try:
            run = log.read_run(self.tenant.roots, self.run_id)
        except UnknownRun:
            return None
        return run if isinstance(run.state, Stopped) else None


def _last_run(events: Sequence[Event]) -> str | None:
    auto_calls = {
        one.call_id for one in events if isinstance(one, ToolCalled) and one.name in AUTO_TOOLS
    }
    found = None
    for one in events:
        if isinstance(one, ToolReturned) and one.call_id in auto_calls and not one.is_error:
            found = _run_of(one.text) or found
    return found


def _run_of(text: str) -> str | None:
    try:
        return AutoRun.model_validate_json(text).run_id
    except ValidationError:
        return None
