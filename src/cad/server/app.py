import subprocess
import sys
from pathlib import Path
from typing import Annotated, NamedTuple

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from pydantic import BaseModel, Field

from cad.sandbox import container, host
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants import store

REPO_ROOT = Path(__file__).resolve().parents[3]
MAX_CODE_CHARS = 256 * 1024
BUILD_VARIANT = (
    "Build one variant from build123d Python code in a sandbox with no network, "
    f"{container.MEMORY_MB // 1024} GB of memory and a {container.WALL_SECONDS} second limit. "
    f"The code runs as a script; {host.CONTRACT}. "
    "Returns the variant id, the outcome (built, build_failed with the error and traceback, "
    "timed_out, out_of_memory or no_result) and the tail of what the code printed. "
    "Building the same code again returns its stored outcome without rebuilding, "
    "except after a timeout."
)


class ServerInfo(BaseModel):
    sha: str
    dirty: bool
    python: str
    tools: list[str]


class GitState(NamedTuple):
    sha: str
    dirty: bool


def git_state(root: Path) -> GitState:
    head = subprocess.run(
        ("git", "rev-parse", "--show-toplevel", "HEAD"),
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    top, _, sha = head.stdout.strip().partition("\n")
    if head.returncode != 0 or Path(top).resolve() != root.resolve():
        return GitState(sha="unknown", dirty=False)
    status = subprocess.run(
        ("git", "status", "--porcelain"),
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    return GitState(sha=sha, dirty=bool(status.stdout.strip()))


def strict_tool(tool: Tool) -> Tool:
    """Reject arguments the tool does not declare; the SDK ignores them by default."""
    arguments = tool.fn_metadata.arg_model
    arguments.model_config["extra"] = "forbid"
    arguments.model_rebuild(force=True)
    tool.parameters = arguments.model_json_schema(by_alias=True)
    return tool


def build_server(variants_root: Path = store.VARIANTS_ROOT) -> MCPServer:
    async def server_info() -> ServerInfo:
        """Report the git SHA the server runs from, whether the tree is dirty, Python and tools."""
        tools = await server.list_tools()
        git = git_state(REPO_ROOT)
        return ServerInfo(
            sha=git.sha,
            dirty=git.dirty,
            python=sys.version.split()[0],
            tools=sorted(tool.name for tool in tools),
        )

    def build_variant(
        code: Annotated[str, Field(max_length=MAX_CODE_CHARS)],
    ) -> store.BuildResult:
        try:
            return store.build_variant(code, variants_root)
        except SandboxUnavailable as error:
            raise ToolError(str(error)) from error

    server = MCPServer(
        "cad",
        tools=[
            strict_tool(Tool.from_function(server_info)),
            strict_tool(Tool.from_function(build_variant, description=BUILD_VARIANT)),
        ],
    )
    return server
