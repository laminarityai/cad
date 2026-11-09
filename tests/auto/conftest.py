import threading
import urllib.request
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import pytest
from mcp import Client
from mcp.server import MCPServer

from cad.auto.log import read_run
from cad.auto.model import AutoRun
from cad.checks.jobs import Admitted, Charge, Refused
from cad.confirmations import http
from cad.confirmations.ballot import Desk
from cad.confirmations.registry import kinds
from cad.context_parts.ingest import ingest
from cad.operations.model import Mode, Tenant
from cad.operations.registry import OPERATIONS
from cad.operations.tools import tools
from cad.records.roots import Roots
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, BuildFailed
from cad.variants import entry


def confirm(url: str) -> None:
    parts = urlsplit(url)
    sent = urllib.request.Request(
        url,
        data=urlencode({"answer": "confirm", "note": ""}).encode(),
        headers={
            "Origin": f"{parts.scheme}://{parts.netloc}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    threading.Thread(target=lambda: urllib.request.urlopen(sent, timeout=5), daemon=True).start()


@dataclass
class Counting:
    refuse: str | None = None
    charges: list[Charge] = field(default_factory=list[Charge])

    def admit(self, charge: Charge) -> Admitted | Refused:
        self.charges.append(charge)
        return Admitted() if self.refuse is None else Refused(self.refuse)


@dataclass
class Session:
    client: Client
    tenant: Tenant
    meter: Counting

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
def meter() -> Counting:
    return Counting()


@pytest.fixture
async def s(tmp_path: Path, meter: Counting) -> AsyncIterator[Session]:
    roots = Roots(tmp_path / "briefs", tmp_path / "projects")
    desk = Desk(roots, kinds(roots), confirm, serve=http.serve, wait_seconds=5)
    tenant = Tenant(
        roots=roots,
        variants=tmp_path / "variants",
        geometry=tmp_path / "geometry",
        desk=desk,
        ingest=ingest,
        meter=meter,
        mode=Mode.AUTO,
    )
    async with Client(MCPServer("cad", tools=tools(tenant, OPERATIONS))) as client:
        yield Session(client, tenant, meter)
