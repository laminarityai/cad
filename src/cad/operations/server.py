import subprocess
from pathlib import Path
from typing import Final, NamedTuple

from pydantic import BaseModel

from cad.operations.model import BOTH, Input, Tenant, operation
from cad.sandbox import host

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
SERVER_INFO: Final = (
    "Report the git SHA the server runs from, whether the tree is dirty, Python and tools."
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


class NoArguments(Input):
    pass


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


def list_materials(tenant: Tenant, arguments: NoArguments) -> MaterialListings:
    del tenant, arguments
    table = host.materials_table()
    return MaterialListings(
        materials=[MaterialListing(key=m.key, name=m.name) for m in table.materials.values()]
    )


OPERATIONS: Final = (
    operation(
        name="list_materials",
        audience=BOTH,
        description=LIST_MATERIALS,
        input=NoArguments,
        output=MaterialListings,
        run=list_materials,
    ),
)
