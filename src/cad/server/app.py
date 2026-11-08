import subprocess
import sys
from pathlib import Path
from typing import Annotated, NamedTuple

from mcp.server import MCPServer
from mcp.server.mcpserver.tools import Tool
from pydantic import BaseModel, Field

from cad.briefs import page
from cad.briefs import store as briefs
from cad.briefs.ballot import OS_OPEN, WAIT_SECONDS, Desk, Opener
from cad.records.roots import HOME_ROOTS, Roots
from cad.sandbox import container, host
from cad.scorecard import requirements, score
from cad.scorecard.model import Scorecard
from cad.server.brief_tools import PLAN_MODE, brief_tools
from cad.server.refusals import agent_facing
from cad.tables.materials import KEY_PATTERN
from cad.variants import entry, store

REPO_ROOT = Path(__file__).resolve().parents[3]
MAX_CODE_CHARS = 256 * 1024
MAX_KEY_CHARS = 64
type MaterialKey = Annotated[
    str, Field(pattern=f"^{KEY_PATTERN.pattern}$", max_length=MAX_KEY_CHARS)
]
BUILD_VARIANT = (
    "Build one variant from build123d Python code in a sandbox with no network, "
    f"{container.MEMORY_MB // 1024} GB of memory and a {container.WALL_SECONDS} second limit. "
    f"The code runs as a script; {host.CONTRACT}. "
    "Returns the variant id, the outcome (built, build_failed with the error and traceback, "
    "timed_out, out_of_memory or no_result) and the tail of what the code printed. "
    "Building the same code again returns its stored outcome without rebuilding, "
    "except after a timeout."
)
RULE = (
    "Only check results decide whether a design is good. In a reply to the user, state a volume, "
    "mass, dimension, bounding box or other measured geometry only when a score_variant result "
    "returned it, and name the check. Numbers your own build code printed and arithmetic you did "
    "yourself are not checks: do not report them as measurements or as confirming the scorecard. "
    "For anything no check measured, say that it was not checked."
)
SCORE_VARIANT = (
    "Score one built variant with the fixed checks closed_solid, interference, mass and "
    "extents (the axis-aligned bounding box in mm), and store the scorecard beside the variant. "
    "When an earlier version of the sandbox stored the variant, score_variant rebuilds its "
    "stored code first and scores the new variant: the scorecard's variant_id is the new id, "
    "and rebuilt_from is the id you passed. It rebuilds even when the earlier build failed, "
    "because the new sandbox may build it. A rebuild that does not build is an error that "
    "gives the build outcome. "
    "Every result has a verdict (pass, fail or unknown), "
    "its measured values, its formula, its sources and its check version. unknown means the "
    "check could not decide, and it is not a pass. "
    "Pass brief_id when the user has a brief. Once the user has confirmed its requirements, the "
    "scorecard's basis is against_brief: for each confirmed requirement it names the check that "
    "decided it, a verdict, and each limit the user confirmed, and unverified_requirements lists "
    "every requirement that no reviewed check covers. The measured value for a limit is the "
    "measure of the same name in that check's result. Before the user confirms, the basis is "
    "awaiting_confirmation and no requirement is judged. Without brief_id the basis is no_brief "
    "and the scorecard covers no requirement. A limit counts as met up to one part in a billion, "
    "an allowance for float noise in unit conversion and not an engineering tolerance. envelope "
    "compares the bounding box of the part as built, never rotated, so it is pass or unknown and "
    "never fail. When you report the scorecard, give every verdict as it states it, with each "
    "check's formula and source, the table version and the basis, and say that every "
    "requirement it did not judge was not checked. "
    "material_key is a key from list_materials. You cannot change a check or the materials table. "
    "Only score_variant writes a stored scorecard, from its own check run, and the server never "
    "reads one back. The file itself is not protected from edits outside the server. "
    "Scoring the same variant and key again gives the same scorecard while the materials table, "
    "the sandbox image and the confirmed requirements are unchanged. Scoring a rebuilt "
    "variant by its new id gives the same scorecard with rebuilt_from empty, and that card "
    "replaces the stored one. " + RULE
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


def build_server(
    variants_root: Path = entry.VARIANTS_ROOT,
    roots: Roots = HOME_ROOTS,
    opener: Opener = OS_OPEN,
    wait_seconds: float = WAIT_SECONDS,
) -> MCPServer:
    desk = Desk(
        roots,
        opener,
        serve=page.serve,
        wait_seconds=wait_seconds,
    )

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
        with agent_facing():
            return store.build_variant(code, variants_root)

    def score_variant(
        variant_id: str, material_key: MaterialKey, brief_id: str | None = None
    ) -> Scorecard:
        with agent_facing():
            assess = score.no_brief
            if brief_id is not None:
                confirmed = briefs.confirmed_requirements(roots, brief_id)
                assess = (
                    requirements.awaiting(brief_id)
                    if confirmed is None
                    else requirements.against(confirmed)
                )
            return score.score_variant(variant_id, material_key, variants_root, assess)

    def list_materials() -> MaterialListings:
        with agent_facing():
            table = host.materials_table()
        return MaterialListings(
            materials=[MaterialListing(key=m.key, name=m.name) for m in table.materials.values()]
        )

    server = MCPServer(
        "cad",
        instructions=RULE + " " + PLAN_MODE,
        tools=[
            strict_tool(tool)
            for tool in (
                Tool.from_function(server_info),
                Tool.from_function(build_variant, description=BUILD_VARIANT),
                Tool.from_function(score_variant, description=SCORE_VARIANT),
                Tool.from_function(list_materials, description=LIST_MATERIALS),
                *brief_tools(roots, desk),
            )
        ],
    )
    return server
