from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from mcp import Client

from cad.auto.log import read_run
from cad.auto.model import AutoRun, Running
from cad.chat.log import Channel, UserSaid, transcript_path
from cad.conversations import store
from cad.conversations.model import ConversationId
from cad.operations.model import Tenant
from cad.operations.tenants import bind
from cad.records.roots import Roots
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.meter import AccountLimitReached, Kind, Reservation
from cad.sandbox.outcome import Build, BuildFailed
from cad.variants import entry
from tests.support.rows import UNDER_150


@dataclass
class Ledger:
    """A meter that records every container it is asked for, and refuses all once `spent`."""

    spent: bool = False
    asked: list[Kind] = field(default_factory=list[Kind])

    def reserve(self, kind: Kind, ceiling_seconds: float) -> Reservation:
        self.asked.append(kind)
        if self.spent:
            raise AccountLimitReached(600, 600, datetime(2026, 11, 10, tzinfo=UTC))
        return Reservation(str(len(self.asked)), "2026-11-09", ceiling_seconds)

    def settle(self, reservation: Reservation, seconds: float) -> None:
        del reservation, seconds


@dataclass
class Session:
    client: Client
    tenant: Tenant
    meter: Ledger
    conversation: ConversationId

    async def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        result = await self.client.call_tool(tool, arguments)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return result.structured_content

    async def refusal(self, tool: str, **arguments: Any) -> str:
        result = await self.client.call_tool(tool, arguments)
        assert result.is_error, result.structured_content
        return result.content[0].model_dump()["text"]

    async def start(self, **arguments: Any) -> AutoRun:
        return AutoRun.model_validate(await self.call("auto_start", **arguments))

    def run(self, run_id: str) -> AutoRun:
        return read_run(self.roots, run_id)

    async def held(self, brief_id: str, run_id: str) -> None:
        held = store.read(self.tenant.conversations, self.conversation)
        assert (held.auto_run, held.stopped_run) == (None, run_id)
        stopped = f"auto run {run_id} has stopped"
        asked = list(self.meter.asked)
        for _ in range(2):
            text = await self.refusal("auto_start", brief_id=brief_id, **PLA_CHOICE)
            assert f"RunRefused: {stopped}" in text, text
            text = await self.refusal("auto_revise", run_id=run_id, code="result = None")
            assert f"RunStopped: {stopped}" in text, text
            text = await self.refusal("auto_ask", run_id=run_id, note="again")
            assert f"RunStopped: {stopped}" in text, text
            text = await self.refusal("build_variant", code="result = None", brief_id=brief_id)
            assert f"RunStopped: {stopped}" in text, text
            text = await self.refusal(
                "score_variant", variant_id="0" * 16, material_key="prusament-pla"
            )
            assert f"RunStopped: {stopped}" in text, text
        assert self.meter.asked == asked
        self.person_acts()
        again = await self.start(brief_id=brief_id, **PLA_CHOICE)
        assert again.run_id != run_id

    def person_acts(self) -> None:
        store.lift_hold(self.tenant.roots, self.tenant.conversations, self.conversation)

    async def confirmed(self, text: str, *requirements: dict[str, Any]) -> str:
        Channel(transcript_path(self.tenant.conversations, self.conversation)).append(
            UserSaid(text=text)
        )
        brief = await self.call("create_brief")
        brief_id = brief["brief_id"]
        await self.propose(brief_id, *requirements)
        answer = await self.call("ask_to_confirm", project_id=brief["project_id"])
        assert answer["status"] == "answered", answer
        return brief_id

    async def propose(self, brief_id: str, *requirements: dict[str, Any]) -> None:
        await self.call("propose_requirements", brief_id=brief_id, requirements=list(requirements))

    def failed_variant(self, code: str) -> str:
        vid = entry.variant_id(code, image_tag(BUILD))
        failed = Build(outcome=BuildFailed(error="NameError", traceback=""), output="")
        entry.save(self.tenant.variants, vid, code, failed, None)
        return vid

    @property
    def bound(self) -> Tenant:
        return bind(self.tenant, self.conversation)

    @property
    def roots(self) -> Roots:
        return self.tenant.roots


TEXT: Final = "A plate under 150 g"
PLA_CHOICE: Final = {
    "material_key": "prusament-pla",
    "material_reason": "PLA is light and prints easily",
}


async def running(s: Session) -> tuple[str, str]:
    brief_id = await s.confirmed(TEXT, UNDER_150)
    run = await s.start(brief_id=brief_id, **PLA_CHOICE)
    assert isinstance(run.state, Running)
    return brief_id, run.run_id
