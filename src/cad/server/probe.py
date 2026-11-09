"""The app step: the server over stdio, and over HTTP with a local agent token, must each report
the SHA that `git rev-parse HEAD` gives."""

import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

import anyio

from cad.accounts.local import LocalIssuer
from cad.operations.server import REPO_ROOT
from cad.server.call import call_tool

UNKNOWN: Final = "unknown"
HOST: Final = "127.0.0.1"
START_SECONDS: Final = 30.0
PROBE_ACCOUNT: Final = "probe"


@contextmanager
def hosted() -> Generator[tuple[str, str]]:
    """Start `cad-http` on a fresh data root and a free port; yield its `/mcp` URL and a token."""
    with tempfile.TemporaryDirectory(prefix="cad-probe-") as root:
        port = free_port()
        base = f"http://{HOST}:{port}"
        command = (sys.executable, "-m", "cad.server.hosted", "--root", root, "--port", str(port))
        server = subprocess.Popen(
            (*command, "--opener", "true"), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        try:
            wait_until_up(base, server)
            yield f"{base}/mcp", LocalIssuer.open(Path(root), base).mint_agent(PROBE_ACCOUNT)
        finally:
            server.terminate()
            server.wait(10)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def wait_until_up(base: str, server: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        if server.poll() is not None:
            stderr = server.stderr.read().decode() if server.stderr else ""
            raise RuntimeError(f"cad-http exited with {server.returncode}: {stderr}")
        try:
            urllib.request.urlopen(f"{base}/.well-known/oauth-protected-resource/mcp", timeout=1)
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise RuntimeError(f"cad-http did not answer on {base} within {START_SECONDS:.0f}s")


def reports_head(transport: str, result: dict[str, Any], head: str) -> bool:
    if result.get("is_error") or result.get("isError"):
        print(f"server_info over {transport} failed: {result}")
        return False
    info = result["structuredContent"]
    reported = info["sha"]
    if UNKNOWN in (reported, head) or reported != head:
        print(
            f"server_info over {transport} reported sha {reported}, git rev-parse HEAD says {head}"
        )
        return False
    print(f"server_info over {transport} sha {reported} dirty={info['dirty']}")
    return True


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
    if not reports_head("stdio", anyio.run(call_tool, "server_info", no_arguments), head):
        return 1
    try:
        with hosted() as (url, token):
            result = anyio.run(call_tool, "server_info", no_arguments, url, token)
    except RuntimeError as error:
        print(f"the HTTP server did not start: {error}")
        return 1
    return 0 if reports_head("http", result, head) else 1


if __name__ == "__main__":
    sys.exit(main())
