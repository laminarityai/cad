import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.accounts.tenants import Tenants
from cad.chat.scripted import Call, Script, Scripted, Step

BASE = "http://127.0.0.1:8765"
ALICE = "user_alice"
BOB = "user_bob"
JSON = {"Content-Type": "application/json"}
TEXT = "A plate under 150 g"
UNDER_150 = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}


def script(*steps: Step) -> Scripted:
    return Scripted(Script(steps=steps), Path.cwd())


def step(text: str = "", *calls: Call) -> Step:
    return Step(text=text, calls=calls)


def call(name: str, **arguments: Any) -> Call:
    return Call(name=name, input=arguments)


@dataclass
class Chat:
    app: Starlette
    local: LocalIssuer
    tenants: Tenants

    def client(self, account: str | None = ALICE) -> httpx2.AsyncClient:
        transport = httpx2.ASGITransport(app=self.app)
        client = httpx2.AsyncClient(transport=transport, base_url=BASE)
        if account is not None:
            client.cookies.set("__session", self.local.mint_person(account))
        return client

    async def conversation(self, client: httpx2.AsyncClient) -> str:
        made = await client.post("/v1/conversations", headers=JSON, content=b"{}")
        assert made.status_code == 201, made.text
        return made.json()["conversation_id"]

    async def say(self, client: httpx2.AsyncClient, cid: str, text: str) -> int:
        sent = await client.post(
            f"/v1/conversations/{cid}/messages", headers=JSON, content=json.dumps({"text": text})
        )
        assert sent.status_code == 202, sent.text
        return sent.json()["seq"]

    async def finish(self) -> None:
        await self.app.state.chat.idle()

    async def events(self, client: httpx2.AsyncClient, cid: str, after: int = 0) -> list[Any]:
        streamed = await client.get(
            f"/v1/conversations/{cid}/stream", params={"follow": "false", "after": after}
        )
        assert streamed.status_code == 200, streamed.text
        return parse(streamed.text)


def parse(text: str) -> list[Any]:
    found: list[Any] = []
    for block in text.split("\n\n"):
        fields = dict(row.split(": ", 1) for row in block.splitlines() if ": " in row)
        if "data" in fields:
            found.append({"seq": int(fields["id"]), **json.loads(fields["data"])})
    return found
