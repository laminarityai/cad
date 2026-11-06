import sys
from typing import Any

import anyio

from cad.server.app import git_sha
from cad.server.call import call_tool


def main() -> int:
    no_arguments: dict[str, Any] = {}
    result = anyio.run(call_tool, "server_info", no_arguments)
    if result.get("is_error") or result.get("isError"):
        print(f"server_info failed: {result}")
        return 1
    reported = result["structuredContent"]["sha"]
    expected = git_sha()
    if reported != expected:
        print(f"server_info reported sha {reported}, expected {expected}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
