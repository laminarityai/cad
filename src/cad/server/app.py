import subprocess
import sys
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.tools import Tool
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]


class ServerInfo(BaseModel):
    sha: str
    python: str
    tools: list[str]


def git_sha() -> str:
    done = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    return done.stdout.strip() if done.returncode == 0 else "unknown"


def strict_tool(tool: Tool) -> Tool:
    """Reject arguments the tool does not declare; the SDK ignores them by default."""
    arguments = tool.fn_metadata.arg_model
    arguments.model_config["extra"] = "forbid"
    arguments.model_rebuild(force=True)
    tool.parameters = arguments.model_json_schema(by_alias=True)
    return tool


def build_server() -> MCPServer:
    async def server_info() -> ServerInfo:
        """Report the git SHA the server runs from, its Python version and its tool names."""
        tools = await server.list_tools()
        return ServerInfo(
            sha=git_sha(),
            python=sys.version.split()[0],
            tools=sorted(tool.name for tool in tools),
        )

    server = MCPServer("cad", tools=[strict_tool(Tool.from_function(server_info))])
    return server
