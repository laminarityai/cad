import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, cast

import anyio
from mcp import Client, StdioServerParameters
from mcp.shared.exceptions import MCPError

SERVER = StdioServerParameters(command=sys.executable, args=["-m", "cad.server"])


async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with Client(SERVER) as client:
        try:
            result = await client.call_tool(name, arguments)
        except MCPError as error:
            return {"is_error": True, "error": str(error)}
        return result.model_dump(mode="json", by_alias=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cad-call", description="Call one tool on the cad server over stdio."
    )
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
    result = anyio.run(call_tool, args.tool, arguments)
    print(json.dumps(result, indent=2))
    return 1 if result.get("is_error") or result.get("isError") else 0


if __name__ == "__main__":
    sys.exit(main())
