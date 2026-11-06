import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from mcp.server import MCPServer
from mcp.server.mcpserver.tools import Tool
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]


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


def build_server() -> MCPServer:
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

    server = MCPServer("cad", tools=[strict_tool(Tool.from_function(server_info))])
    return server
