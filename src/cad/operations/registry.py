import sys
from typing import Final

from cad.operations import briefs, confirmation, knowledge, research, scorecards, variants
from cad.operations import server as server_operations
from cad.operations.model import BOTH, Operation, Tenant, operation
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
    *knowledge.OPERATIONS,
    *research.OPERATIONS,
)
