import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, cast

import anyio
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.exceptions import MCPError

SERVER = StdioServerParameters(command=sys.executable, args=["-m", "cad.server"])


async def call_tool(
    name: str, arguments: dict[str, Any], url: str | None = None, token: str | None = None
) -> dict[str, Any]:
    """Over stdio by default, or to `url` over streamable HTTP with `token` as the bearer."""
    server = SERVER
    if url is not None:
        headers = {} if token is None else {"Authorization": f"Bearer {token}"}
        server = streamable_http_client(url, http_client=create_mcp_http_client(headers))
    async with Client(server) as client:
        try:
            result = await client.call_tool(name, arguments)
        except MCPError as error:
            return {"is_error": True, "error": str(error)}
        return result.model_dump(mode="json", by_alias=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cad-call", description="Call one tool on the cad server, over stdio or HTTP."
    )
    parser.add_argument("--url", help="an HTTP server's /mcp URL; stdio when left out")
    parser.add_argument("--token", help="the bearer token for --url, such as cad-token prints")
    parser.add_argument("tool")
    parser.add_argument("arguments", help="tool arguments as a JSON object")
    args = parser.parse_args(argv)
    try:
        parsed: object = json.loads(args.arguments)
    except json.JSONDecodeError as error:
        parser.error(f"arguments are not valid JSON: {error}")
    if not isinstance(parsed, dict):
        parser.error("arguments must be a JSON object")
    arguments = cast(dict[str, Any], parsed)
    result = anyio.run(call_tool, args.tool, arguments, args.url, args.token)
    print(json.dumps(result, indent=2))
    return 1 if result.get("is_error") or result.get("isError") else 0


if __name__ == "__main__":
    sys.exit(main())
