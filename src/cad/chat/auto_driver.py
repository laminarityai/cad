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
from cad.operations.guidance import CHAT_AUTO_NUDGE
from cad.operations.model import Tenant
from cad.projects.model import ProjectRefused
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import Member, SetRefused

AUTO_TOOLS: Final = frozenset({"auto_start", "auto_revise", "auto_ask"})
MAX_NUDGES: Final = 3
# Every later turn reads the same damaged log and fails here, so only on this path is the chat
# itself done. A run damaged after its report was posted leaves the chat working.
ENDED: Final = (
    "auto run {run_id}'s records failed the server's integrity check, so Auto cannot go on "
    "and this chat cannot take more messages; start a new project to carry on"
)


@dataclass
class AutoDriver:
    tenant: Tenant
    run_id: str | None
    reported: bool = False
    nudges: int = 0

    @staticmethod
    def resume(tenant: Tenant, events: Sequence[Event]) -> "AutoDriver":
        cid = tenant.conversation
        held = None if cid is None else store.read(tenant.conversations, cid)
        followed = None if held is None else held.auto_run or held.stopped_run
        run_id = followed or _last_run(events)
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
        except TamperedRun:
            return TurnFailed(message=ENDED.format(run_id=self.run_id))
        if run is None:
            return None
        self.reported = True
        assert isinstance(run.state, Stopped)
        state = run.state
        brief_id = state.start.brief_id
        option = self._option(brief_id, state.history[-1].code_sha256) if state.history else None
        said = report(state.history, state.reason, self._statements(brief_id), option)
        return StopReport(run_id=run.run_id, reason=state.reason.kind, report=said)

    def nudge(self) -> str | None:
        if self.reported or self.run_id is None or self.nudges >= MAX_NUDGES:
            return None
        if self._stopped() is not None:
            return None
        self.nudges += 1
        return CHAT_AUTO_NUDGE.format(run_id=self.run_id)

    def _statements(self, brief_id: str) -> dict[str, str]:
        roots = self.tenant.roots
        try:
            proposals = briefs.read_state(roots, brief_id).proposals
            names = plain_names(roots, brief_id)
        except (BriefRefused, ProjectRefused):
            return {}
        return {r.id: describe(r, names) for one in proposals for r in one.requirements}

    def _option(self, brief_id: str, code_sha256: str) -> str | None:
        """The name the person sees for the slot that holds this code, and its revision."""
        roots = self.tenant.roots
        try:
            held = variant_sets.members(roots.projects, variant_sets.set_key(roots, brief_id))
        except (BriefRefused, ProjectRefused, SetRefused):
            return None
        return next((name for member in held if (name := _named(member, code_sha256))), None)

    def _stopped(self) -> AutoRun | None:
        if self.run_id is None:
            return None
        try:
            run = log.read_run(self.tenant.roots, self.run_id)
        except UnknownRun:
            return None
        return run if isinstance(run.state, Stopped) else None


def _named(member: Member, code_sha256: str) -> str | None:
    labels = [one.option.label for one in member.revisions if one.option is not None]
    label = labels[-1] if labels else f"Option {member.slot}"
    numbers = [
        n for n, one in enumerate(member.revisions, start=1) if one.code_sha256 == code_sha256
    ]
    return f"{label}, revision {numbers[-1]}" if numbers else None


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
