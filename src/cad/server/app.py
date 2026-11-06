import subprocess
import sys
from pathlib import Path
from typing import Annotated, NamedTuple

import yaml
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from pydantic import BaseModel, Field

from cad.sandbox import container, host
from cad.sandbox.container import first_line
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard import score
from cad.scorecard.model import Scorecard
from cad.tables.materials import load_materials
from cad.variants import entry, store

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
SCORE_VARIANT = (
    "Score one built variant with the fixed checks closed_solid, interference and mass, and "
    "store the scorecard beside the variant. Every result has a verdict (pass, fail or unknown), "
    "its measured values, its formula, its sources and its check version. unknown means the "
    "check could not decide, and it is not a pass. "
    "The scorecard names the table version and the sandbox image digest, and it says that phase 1 "
    "reads no requirements from the brief. Quote every verdict as the scorecard gives it. "
    "material_key is a key from list_materials. You cannot change a check, the materials table "
    "or a stored scorecard. Scoring the same variant and key again gives the same scorecard."
)
LIST_MATERIALS = (
    "List the material keys that score_variant accepts, each with its name. "
    "The checks look the density up by exact key. No value is returned, so there is nothing "
    "to copy."
)


class ServerInfo(BaseModel):
    sha: str
    dirty: bool
    python: str
    tools: list[str]


class MaterialListing(BaseModel):
    key: str
    name: str


class MaterialListings(BaseModel):
    materials: list[MaterialListing]


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


def build_server(variants_root: Path = entry.VARIANTS_ROOT) -> MCPServer:
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

    def score_variant(variant_id: str, material_key: str) -> Scorecard:
        try:
            return score.score_variant(variant_id, material_key, variants_root)
        except entry.VariantRefused as error:
            raise ToolError(f"{type(error).__name__}: {error}") from error
        except SandboxUnavailable as error:
            raise ToolError(str(error)) from error

    def list_materials() -> MaterialListings:
        try:
            table = load_materials()
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise ToolError(f"cannot read the materials table: {first_line(str(error))}") from error
        return MaterialListings(
            materials=[MaterialListing(key=m.key, name=m.name) for m in table.materials.values()]
        )

    server = MCPServer(
        "cad",
        tools=[
            strict_tool(Tool.from_function(server_info)),
            strict_tool(Tool.from_function(build_variant, description=BUILD_VARIANT)),
            strict_tool(Tool.from_function(score_variant, description=SCORE_VARIANT)),
            strict_tool(Tool.from_function(list_materials, description=LIST_MATERIALS)),
        ],
    )
    return server
