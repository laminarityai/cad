import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from cad.accounts.clerk import PUBLIC_URL, PUBLISHABLE_KEY
from cad.accounts.local import LocalIssuer
from tests.support.chat import ALICE, JSON

EXIT_SECONDS = 8.0


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def wait_until_up(url: str, server: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        assert server.poll() is None, "cad-http exited before it served"
        try:
            urllib.request.urlopen(f"{url}/.well-known/oauth-protected-resource/mcp", timeout=1)
            return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.2)
    raise AssertionError("cad-http did not start")


def open_stream(port: int, cid: str, token: str) -> socket.socket:
    stream = socket.create_connection(("127.0.0.1", port), timeout=10)
    stream.sendall(
        f"GET /v1/conversations/{cid}/stream HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        f"Cookie: __session={token}\r\n\r\n".encode()
    )
    head = b""
    while b"\r\n\r\n" not in head:
        head += stream.recv(4096)
    assert head.startswith(b"HTTP/1.1 200"), head
    return stream


def test_sigterm_with_a_chat_stream_open_ends_the_stream_and_exits_in_seconds(
    tmp_path: Path,
) -> None:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    environ = {k: v for k, v in os.environ.items() if k not in (PUBLIC_URL, PUBLISHABLE_KEY)}
    main = "import sys; from cad.server.hosted import main; sys.exit(main())"
    server = subprocess.Popen(
        [sys.executable, "-c", main, "--root", str(tmp_path), "--port", str(port)],
        env=environ,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_until_up(url, server)
        token = LocalIssuer.open(tmp_path, url).mint_person(ALICE)
        made = urllib.request.Request(
            f"{url}/v1/conversations",
            data=b"{}",
            headers={**JSON, "Cookie": f"__session={token}"},
        )
        cid = json.load(urllib.request.urlopen(made, timeout=10))["conversation_id"]
        stream = open_stream(port, cid, token)
        sent = time.monotonic()
        server.terminate()
        server.wait(timeout=EXIT_SECONDS)
        assert time.monotonic() - sent < EXIT_SECONDS
        stream.settimeout(1)
        while stream.recv(4096):
            pass
        stream.close()
    finally:
        server.kill()
        server.wait()
