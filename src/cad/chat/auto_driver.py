"""What the chat does for an Auto run, beyond what the agent does.

The server decides when a run stops and refuses every call after it (ADR-0010), so the driver
holds no rule of its own. It does two things the server cannot. It reads the run's signed log
after each tool call and posts the stop's report as soon as the run stops, whoever stopped it:
the agent, a passing scorecard, the usage cap, or the person's Stop while the turn was running.
And it reminds an agent that ended its message with the run still running to call `auto_revise`
or `auto_ask`, a few times at most.
"""

from dataclasses import dataclass
from typing import Final

from pydantic import ValidationError

from cad.auto import log
from cad.auto.model import AutoRun, Stopped, UnknownRun
from cad.chat.log import StopReport
from cad.chat.model import ToolResult, ToolUse
from cad.conversations import store
from cad.conversations.model import Mode
from cad.operations.model import Tenant

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
    def resume(tenant: Tenant) -> "AutoDriver":
        """Follow the run the conversation holds, so a message that continues a run is watched. A
        run that had already stopped before this turn was reported by the turn that stopped it."""
        cid = tenant.conversation
        held = None if cid is None else store.read(tenant.conversations, cid)
        driver = AutoDriver(tenant, None if held is None else held.auto_run)
        driver.reported = driver._stopped() is not None
        return driver

    def observe(self, call: ToolUse, result: ToolResult) -> None:
        if call.name not in AUTO_TOOLS:
            return
        if not result.is_error:
            try:
                run_id = AutoRun.model_validate_json(result.text).run_id
            except ValidationError:
                return
            if run_id != self.run_id:
                self.run_id, self.reported, self.nudges = run_id, False, 0
        elif self.run_id is None and isinstance(call.input.get("run_id"), str):
            self.run_id = str(call.input["run_id"])

    def stop_report(self) -> StopReport | None:
        """The report of a stop this turn has not yet posted, read from the signed run log."""
        if self.reported:
            return None
        run = self._stopped()
        if run is None:
            return None
        self.reported = True
        assert isinstance(run.state, Stopped)
        return StopReport(run_id=run.run_id, reason=run.state.reason.kind, report=run.state.report)

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

    def _stopped(self) -> AutoRun | None:
        if self.run_id is None:
            return None
        try:
            run = log.read_run(self.tenant.roots, self.run_id)
        except UnknownRun:
            return None
        return run if isinstance(run.state, Stopped) else None
