import sys
from collections.abc import Mapping
from typing import Final

from cad.operations import (
    agent_checks,
    auto,
    briefs,
    confirmation,
    context_parts,
    conversations,
    exports,
    files,
    geometry,
    knowledge,
    reads,
    research,
    scorecards,
    selections,
    variants,
)
from cad.operations import server as server_operations
from cad.operations.model import BOTH, Operation, Tenant, operation
from cad.operations.routes import Served
from cad.operations.server import REPO_ROOT, NoArguments, ServerInfo, git_state
from cad.operations.tools import agent_operations


def server_info(tenant: Tenant, arguments: NoArguments) -> ServerInfo:
    del tenant, arguments
    git = git_state(REPO_ROOT)
    return ServerInfo(
        sha=git.sha,
        dirty=git.dirty,
        python=sys.version.split()[0],
        tools=sorted(one.name for one in agent_operations(OPERATIONS)),
    )


OPERATIONS: Final[tuple[Operation, ...]] = (
    operation(
        name="server_info",
        audience=BOTH,
        description=server_operations.SERVER_INFO,
        input=NoArguments,
        output=ServerInfo,
        run=server_info,
    ),
    *variants.OPERATIONS,
    *scorecards.OPERATIONS,
    *server_operations.OPERATIONS,
    *briefs.OPERATIONS,
    *confirmation.OPERATIONS,
    *context_parts.OPERATIONS,
    *files.OPERATIONS,
    *knowledge.OPERATIONS,
    *research.OPERATIONS,
    *agent_checks.OPERATIONS,
    *auto.OPERATIONS,
    *conversations.OPERATIONS,
    *geometry.OPERATIONS,
    *exports.OPERATIONS,
    *reads.OPERATIONS,
    *selections.OPERATIONS,
)

ROUTES: Final[Mapping[str, Served]] = {
    "server_info": Served("/v1/server"),
    "list_materials": Served("/v1/materials"),
    "search_knowledge": Served("/v1/knowledge"),
    "list_requirements": Served("/v1/briefs/{brief_id}"),
    "list_projects": Served("/v1/projects"),
    "project": Served("/v1/projects/{project_id}"),
    "variant_set": Served("/v1/projects/{project_id}/briefs/{brief_id}/set"),
    "scorecard": Served("/v1/variants/{variant_id}/scorecard"),
    "view": Served("/v1/variants/{variant_id}"),
    "geometry": Served("/v1/variants/{variant_id}/geometry"),
    "mesh": Served(reads.MESH_PATH, immutable=True),
    "export": Served("/v1/variants/{variant_id}/exports/{format}"),
    "export_file": Served(exports.EXPORT_PATH, immutable=True, download=True),
    "conversation": Served("/v1/conversations/{conversation_id}"),
    "auto_stop": Served("/v1/auto/{run_id}/stop", method="POST"),
}
