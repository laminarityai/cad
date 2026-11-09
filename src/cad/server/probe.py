import subprocess
import sys
from typing import Any

import anyio

from cad.operations.server import REPO_ROOT
from cad.server.call import call_tool

UNKNOWN = "unknown"


def main() -> int:
    try:
        head = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError) as error:
        print(f"git rev-parse HEAD failed in {REPO_ROOT}: {error}")
        return 1
    no_arguments: dict[str, Any] = {}
    result = anyio.run(call_tool, "server_info", no_arguments)
    if result.get("is_error") or result.get("isError"):
        print(f"server_info failed: {result}")
        return 1
    info = result["structuredContent"]
    reported = info["sha"]
    if UNKNOWN in (reported, head) or reported != head:
        print(f"server_info reported sha {reported}, git rev-parse HEAD says {head}")
        return 1
    print(f"server_info sha {reported} dirty={info['dirty']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
