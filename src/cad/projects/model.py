import re
import secrets
from typing import Final, NewType

from cad.errors import NotFound, Refused

ProjectId = NewType("ProjectId", str)
NewProjectId = NewType("NewProjectId", ProjectId)
NEW_PROJECT_ID: Final = re.compile(r"^p-[0-9a-f]{16}$")
PROJECT_ID: Final = re.compile(r"^(p|pb)-[0-9a-f]{16}$")
PROJECT_ID_CHARS: Final = 19
LEGACY: Final = "pb-"


class ProjectRefused(Refused):
    pass


class UnknownProject(ProjectRefused, NotFound):
    pass


class TamperedProject(ProjectRefused):
    pass


class ProjectBusy(ProjectRefused):
    pass


def parse_project_id(raw: str) -> ProjectId:
    if PROJECT_ID.fullmatch(raw) is None:
        raise UnknownProject(f"a project id is p- or pb- and 16 lowercase hex digits, not {raw!r}")
    return ProjectId(raw)


def new_project_id() -> NewProjectId:
    return NewProjectId(ProjectId(f"p-{secrets.token_hex(8)}"))


def legacy_project(brief_id: str) -> ProjectId:
    return ProjectId(f"{LEGACY}{brief_id}")
