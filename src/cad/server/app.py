import subprocess
import sys
from pathlib import Path
from typing import Annotated, NamedTuple

from mcp.server import MCPServer
from mcp.server.mcpserver.tools import Tool
from pydantic import BaseModel, Field

from cad.agent_measurements import run as own
from cad.briefs import store as briefs
from cad.confirmations import http
from cad.confirmations.ballot import OS_OPEN, WAIT_SECONDS, Desk, Opener
from cad.confirmations.registry import kinds
from cad.records.roots import HOME_ROOTS, Roots
from cad.sandbox import container, host
from cad.scorecard import material, requirements, score
from cad.server.brief_tools import PLAN_MODE, brief_tools
from cad.server.confirmation_tools import confirmation_tools
from cad.server.knowledge_tools import knowledge_tools
from cad.server.refusals import agent_facing
from cad.server.research_tools import brief_table, research_tools, with_research
from cad.tables.materials import KEY_PATTERN
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import MAX_MEMBERS, SetBuildResult, SlotRefused
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
    "except after a timeout. "
    "Pass brief_id once the user has confirmed the brief's requirements: a built variant then "
    f"joins the brief's variant set, which holds up to {MAX_MEMBERS} variants for the user to "
    "compare, and variant_set names its slot and revision. Build 3 to 5 different variants, each "
    "in its own slot. To change a variant the user asked about, such as making a wall thicker, "
    f"build the edited code with brief_id and that variant's slot, 1 to {MAX_MEMBERS}: it becomes "
    "the slot's next revision, and the set shows it in place of the old one, which stays in the "
    "slot's history. Without slot, code already shown in a slot keeps that slot, and new code "
    "takes the lowest free slot. A build for a brief with no confirmed requirements, for new "
    "code with no slot when every slot is taken, or for code that another slot already shows, "
    "is refused before it starts. If the set changes while a build runs so that it cannot take "
    "the code, the build finishes and is stored, but the error says it joined no set and names "
    "its variant id. Without brief_id the variant joins no set, and slot is refused."
)
RULE = (
    "Only check results decide whether a design is good. In a reply to the user, state a volume, "
    "mass, dimension, bounding box or other measured geometry only when a score_variant result "
    "returned it, and name the check. Numbers your own build code printed and arithmetic you did "
    "yourself are not checks: do not report them as measurements or as confirming the scorecard. "
    "For anything no check measured, say that it was not checked."
)
RESEARCH = (
    "A material value the table lacks is researched, not left unknown. When a scorecard's "
    "research lists a request, answer each one with submit_research: a public page and a "
    "quote from it, never a number of your own. Then score again. A result labelled "
    "researched rests on a value the server read from that quote: report a pass on it as "
    '"passes on researched data" and name the source. When a page is refused, try another. '
    "When a scorecard has a research_problem, tell the user what it says and research "
    "nothing for that project: only the operator can fix it."
)
TEST_MODE = (
    "Test mode is deeper analysis of one variant the user picks, for example when they ask "
    "whether it will hold a load or how long it takes to print. If the user states a load, a "
    "print process or a print time that no confirmed requirement holds, propose it: a load as "
    "min_safety_factor or max_deflection, which the fea check decides, and anything else as "
    "unchecked when no check decides it. Have the user confirm before you score. Words "
    "that are not in the brief go into a new brief in the same project first. Then score only "
    "that variant, with its brief_id. A scorecard with pending checks is not finished: do not "
    "state a pending check's result, and call score_variant again with the same arguments to "
    "wait for it. Report only what the checks returned, and for a load, the fea verdict and "
    "its measures. Do not estimate a strength, a deflection or a print time yourself: when no "
    "check returned it, say it was not checked. When fea is unknown because the table lacks a "
    "material value, answer the card's research requests and score again before you report."
)
NOT_VERIFIED = (
    "A scorecard's not_verified list holds measurements your own code made. Report each one as "
    '"my own measurement, not verified". Never call it a pass or a fail, never say it meets or '
    "misses a requirement, and say that its requirement was not checked. Do not do arithmetic "
    "on it to reach a verdict."
)
OWN_MEASUREMENTS = (
    "For a confirmed requirement of kind unchecked, you may pass own_measurements: up to "
    f"{own.MAX_SNIPPETS} entries, each a requirement_id, a short title and build123d Python code "
    f"of at most {own.MAX_CODE_CHARS // 1024} KiB. The code sees `part`, the scored shape, and "
    "calls report(name, value, unit) with a name of lowercase letters, digits and underscores, "
    f"a finite number and a unit of {', '.join(own.UNIT_NAMES)}. It runs in the build sandbox "
    f"after the checks, all entries in one run of at most {own.WALL_SECONDS} seconds. Each entry "
    'becomes a not_verified row labelled "agent\'s own measurement, not verified": its values, '
    "or failed with the reason. The row has no verdict, its requirement stays in "
    "unverified_requirements, and no check or requirement reads it. own_measurements without a "
    "confirmed brief, or naming a requirement a check decides, is refused and nothing is scored. "
)
SCORE_VARIANT = (
    "Score one built variant with the fixed checks closed_solid, interference, mass and "
    "extents (the axis-aligned bounding box in mm), and store the scorecard beside the variant. "
    "Each load case of a confirmed min_safety_factor or max_deflection requirement also runs "
    "the fea check, in the background, once per load case: its result carries the load case "
    "id as instance. Until it finishes, the card lists it under pending, the result is a "
    "pending entry with no verdict, and each requirement it decides is waiting. A scorecard "
    "with pending checks is not finished: do not state a pending check's result, and call "
    "score_variant again with the same arguments to wait for it. fea states its error: a "
    "measure within that error of a confirmed limit leaves the requirement unknown. "
    "When an earlier version of the sandbox stored the variant, score_variant rebuilds its "
    "stored code first and scores the new variant: the scorecard's variant_id is the new id, "
    "and rebuilt_from is the id you passed. It rebuilds even when the earlier build failed, "
    "because the new sandbox may build it. A rebuild that does not build is an error that "
    "gives the build outcome. "
    "Every result has a verdict (pass, fail or unknown), "
    "its measured values, its formula, its sources and its check version. unknown means the "
    "check could not decide, and it is not a pass. "
    "Each result's reads say, for each material value the check takes, whether the table "
    "cites it, the project researched it (with the url and quote), or the table lacks it. "
    "When a check read a missing material value, the card's research holds a request for it: "
    "answer it with submit_research and score again. A result or requirement whose basis is "
    'researched rests on a researched value: report its pass as "passes on researched data", '
    "naming the field, url and quote. Missing geometry is never researched. "
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
    "material_key is a key from list_materials. When the user confirmed a made_of requirement "
    "for the brief, pass that key: any other material_key is refused and nothing is scored. "
    "The card's material says which key was used and what set it, the confirmed requirement or "
    "your argument. When your argument set it, say so wherever a result rests on the material. "
    "You cannot change a check or the materials table. "
    "Only score_variant writes a stored scorecard, from its own check run, and the server never "
    "reads one back. The file itself is not protected from edits outside the server. "
    "Scoring the same variant and key again gives the same scorecard while the materials table, "
    "the sandbox image and the confirmed requirements are unchanged. Scoring a rebuilt "
    "variant by its new id gives the same scorecard with rebuilt_from empty, and that card "
    "replaces the stored one. In Test mode, score only the variant the user picked. "
    + OWN_MEASUREMENTS
    + RULE
    + " "
    + NOT_VERIFIED
)
LIST_MATERIALS = (
    "List the material keys that score_variant accepts, each with its name. "
    "The checks look each value up by exact key. No value is returned, so there is nothing "
    "to copy. A value the table lacks comes back on the scorecard as a research request."
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
    desk = Desk(roots, kinds(roots), opener, serve=http.serve, wait_seconds=wait_seconds)

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
        brief_id: str | None = None,
        slot: int | None = None,
    ) -> SetBuildResult:
        with agent_facing():
            if brief_id is not None:
                return variant_sets.build_into_set(roots, variants_root, brief_id, code, slot)
            if slot is not None:
                raise SlotRefused(
                    "slot names a place in a brief's variant set, so pass brief_id too"
                )
            built = store.build_variant(code, variants_root)
        return SetBuildResult(
            variant_id=built.variant_id, outcome=built.outcome, output=built.output
        )

    def score_variant(
        variant_id: str,
        material_key: MaterialKey,
        brief_id: str | None = None,
        own_measurements: own.OwnMeasurements | None = None,
    ) -> material.ReportedScorecard:
        with agent_facing():
            assess, demand = score.no_brief, score.NO_DEMAND
            confirmed = None
            if brief_id is not None:
                confirmed = briefs.confirmed_requirements(roots, brief_id)
                if confirmed is None:
                    assess = requirements.awaiting(brief_id)
                else:
                    assess, demand = requirements.against(confirmed), requirements.demand(confirmed)
            material.refuse_other_material(confirmed, material_key)
            table = brief_table(roots, brief_id)
            if own_measurements:
                own.refuse_unless_unchecked(confirmed, own_measurements)
            scored = score.score_variant(
                variant_id, material_key, variants_root, assess, demand=demand, table=table.table
            )
            card = with_research(material.reported(scored, confirmed), table, brief_id)
            if own_measurements:
                rows = own.measure(variants_root, card.variant_id, own_measurements)
                card = own.attach(card, rows)
            score.store(card, variants_root)
        return card

    def list_materials() -> MaterialListings:
        with agent_facing():
            table = host.materials_table()
        return MaterialListings(
            materials=[MaterialListing(key=m.key, name=m.name) for m in table.materials.values()]
        )

    server = MCPServer(
        "cad",
        instructions=" ".join((RULE, PLAN_MODE, TEST_MODE, RESEARCH, NOT_VERIFIED)),
        tools=[
            strict_tool(tool)
            for tool in (
                Tool.from_function(server_info),
                Tool.from_function(build_variant, description=BUILD_VARIANT),
                Tool.from_function(score_variant, description=SCORE_VARIANT),
                Tool.from_function(list_materials, description=LIST_MATERIALS),
                *brief_tools(roots),
                *confirmation_tools(roots, desk),
                *knowledge_tools(),
                *research_tools(roots),
            )
        ],
    )
    return server
