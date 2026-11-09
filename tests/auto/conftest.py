from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from mcp import Client
from mcp.server import MCPServer

from cad.auto.log import read_run
from cad.auto.model import AutoRun
from cad.confirmations.waiting import Bell, Door
from cad.context_parts.ingest import ingest
from cad.operations.model import Mode, Tenant
from cad.operations.registry import OPERATIONS
from cad.operations.tools import tools
from cad.records.roots import Roots
from cad.sandbox import container
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.meter import AccountLimitReached, Kind, Reservation
from cad.sandbox.outcome import Build, BuildFailed
from cad.server.app import LOCAL, LocalPage
from cad.variants import entry

if TYPE_CHECKING:
    from conftest import Person


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

    async def confirmed(self, text: str, *requirements: dict[str, Any]) -> str:
        brief = await self.call("create_brief", text=text)
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
    def roots(self) -> Roots:
        return self.tenant.roots


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The name of each container that reached `docker run`."""
    names: list[str] = []

    def attend(name: str, argv: tuple[str, ...], stdin: bytes, wall_seconds: int) -> None:
        del argv, stdin, wall_seconds
        names.append(name)
        raise container.SandboxUnavailable("this test starts no container")

    monkeypatch.setattr(container, "attend", attend)
    return names


@pytest.fixture
def meter() -> Ledger:
    return Ledger()


@pytest.fixture
async def s(tmp_path: Path, meter: Ledger, person: "Person") -> AsyncIterator[Session]:
    person.answer = "confirm"
    roots = Roots(tmp_path / "briefs", tmp_path / "projects")
    page = LocalPage(person, lambda: tenant)
    tenant = Tenant(
        account=LOCAL,
        roots=roots,
        variants=tmp_path / "variants",
        geometry=tmp_path / "geometry",
        bell=Bell(),
        door=Door(open_page=page.open, wait_seconds=5),
        ingest=ingest,
        meter=meter,
        mode=Mode.AUTO,
    )
    async with Client(MCPServer("cad", tools=tools(lambda: tenant, OPERATIONS))) as client:
        yield Session(client, tenant, meter)
