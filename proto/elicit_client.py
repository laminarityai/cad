"""THROWAWAY. A scripted MCP client that answers the prototype's elicitation itself.

Usage: uv run python proto/elicit_client.py <auto|legacy> <accept|decline|cancel>
"""

import json
import sys

import anyio
import mcp_types as types
from mcp import Client

from cad.server.call import SERVER

ACTION = sys.argv[2]


async def on_elicit(ctx: object, params: types.ElicitRequestParams) -> types.ElicitResult:
    seen = params.model_dump(mode="json", by_alias=True, exclude_none=True)
    print("ELICIT RECEIVED:", json.dumps(seen), file=sys.stderr)
    if ACTION == "accept":
        return types.ElicitResult(action="accept", content={"confirm": True})
    return types.ElicitResult(action=ACTION)  # type: ignore[arg-type]


async def main() -> None:
    async with Client(SERVER, mode=sys.argv[1], elicitation_callback=on_elicit) as client:  # type: ignore[arg-type]
        result = await client.call_tool(
            "proto_confirm_elicit", {"requirements": ["max mass 50 g", "fits 60x40 mm"]}
        )
        print(json.dumps(result.structured_content))


anyio.run(main)
