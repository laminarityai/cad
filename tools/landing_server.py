"""The scratch server the landing capture drives, and the checks that come before it starts."""

import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Final

import landing_media as media

ROOT: Final = Path(__file__).resolve().parents[1]
DRY: Final = ROOT / "tools" / "landing_dry" / "script.json"
KEY_FILE: Final = Path.home() / ".config" / "cad" / "anthropic.env"
FREE_BYTES: Final = 700_000_000


class Missed(Exception):
    pass


def say(text: str) -> None:
    print(text, flush=True)


def preflight(dry: bool, port: int) -> None:
    for tool in ("ffmpeg", "cwebp", "docker"):
        if shutil.which(tool) is None:
            raise Missed(f"{tool} is not on PATH")
    if subprocess.run(["docker", "info"], capture_output=True, check=False).returncode != 0:
        raise Missed("Docker does not answer. ~/.claude/bin/restart-docker.sh restarts it.")
    if shutil.disk_usage(ROOT).free < FREE_BYTES:
        raise Missed("free disk is under 0.7 GB")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise Missed(f"port {port} is taken, and 8765 is the operator's own server")
    if not dry and not KEY_FILE.is_file():
        raise Missed(f"no key at {KEY_FILE}")


def key() -> str:
    """The key in the key file. It goes to the server's environment and nowhere else."""
    for line in KEY_FILE.read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "ANTHROPIC_API_KEY":
            return value.strip()
    raise Missed(f"{KEY_FILE} has no ANTHROPIC_API_KEY line")


def docker_host() -> str:
    """Where Docker listens, read in the real HOME so a server on a scratch HOME finds it."""
    found = subprocess.run(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return found.stdout.strip() if found.returncode == 0 else ""


class Server:
    """`cad-http` on a scratch HOME. It never touches the real one."""

    def __init__(self, work: Path, port: int, dry: bool, budget: float) -> None:
        self.url = f"http://127.0.0.1:{port}"
        self.data = work / "root"
        self.home = work / "home"
        self.log = work / "server.log"
        self.budget = budget
        self.over = threading.Event()
        self.home.mkdir(parents=True)
        env = {
            "PATH": f"{Path(sys.executable).parent}:/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin",
            "HOME": str(self.home),
        }
        host = docker_host()
        if host:
            env["DOCKER_HOST"] = host
        if dry:
            env["CAD_CHAT_MODEL"] = f"scripted:{DRY}"
        else:
            env["ANTHROPIC_API_KEY"] = key()
        out = self.log.open("w")
        self.process = subprocess.Popen(
            [
                str(Path(sys.executable).parent / "cad-http"),
                "--root",
                str(self.data),
                "--port",
                str(port),
                "--opener",
                "true",
            ],
            cwd=ROOT,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
        )
        threading.Thread(target=self.guard, daemon=True).start()

    def spent(self) -> float:
        return media.cost(self.log.read_text().splitlines())

    def guard(self) -> None:
        while self.process.poll() is None:
            if self.spent() > self.budget:
                self.over.set()
                self.process.terminate()
                return
            time.sleep(2)

    def wait_ready(self) -> None:
        for _ in range(120):
            if self.process.poll() is not None:
                raise Missed("the server stopped at start")
            if self.data.joinpath("local-issuer.pem").exists() and self.reachable():
                return
            time.sleep(1)
        raise Missed("the server did not answer in 2 minutes")

    def reachable(self) -> bool:
        host, port = self.url.removeprefix("http://").split(":")
        with socket.socket() as probe:
            return probe.connect_ex((host, int(port))) == 0

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(30)
            except subprocess.TimeoutExpired:
                self.process.kill()
