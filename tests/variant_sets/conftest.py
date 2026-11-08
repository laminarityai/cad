import threading
import urllib.request
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import pytest
from mcp import Client

from cad.records.roots import Roots
from cad.server.app import build_server

TEXT = "A plate under 150 g"
UNDER_150 = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}


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
class Session:
    client: Client
    tmp: Path

    async def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        result = await self.client.call_tool(tool, arguments)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return result.structured_content

    async def refusal(self, tool: str, **arguments: Any) -> str:
        result = await self.client.call_tool(tool, arguments)
        assert result.is_error
        return result.content[0].model_dump()["text"]

    @property
    def roots(self) -> Roots:
        return Roots(self.tmp / "briefs", self.tmp / "projects")

    async def proposed_brief(self) -> str:
        brief_id = (await self.call("create_brief", text=TEXT))["brief_id"]
        await self.call("propose_requirements", brief_id=brief_id, requirements=[UNDER_150])
        return brief_id

    async def confirm(self, brief_id: str) -> None:
        listed = await self.call("list_requirements", brief_id=brief_id)
        answer = await self.call("ask_to_confirm", project_id=listed["project_id"])
        assert answer["status"] == "answered", answer

    async def confirmed_brief(self) -> str:
        brief_id = await self.proposed_brief()
        await self.confirm(brief_id)
        return brief_id


@pytest.fixture
async def s(tmp_path: Path) -> AsyncIterator[Session]:
    server = build_server(
        tmp_path / "variants",
        Roots(tmp_path / "briefs", tmp_path / "projects"),
        opener=confirm,
        wait_seconds=5,
    )
    async with Client(server) as client:
        yield Session(client, tmp_path)
