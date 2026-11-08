import re
import secrets
from typing import Annotated, Final, NewType

from pydantic import BaseModel, ConfigDict, StringConstraints

from cad.briefs.model import BriefId

ProjectId = NewType("ProjectId", str)
PROJECT_ID: Final = re.compile(r"(p|pb)-[0-9a-f]{16}")
LEGACY: Final = "pb-"


class ProjectRefused(Exception):
    pass


class UnknownProject(ProjectRefused):
    pass


class Membership(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: Annotated[ProjectId, StringConstraints(pattern=PROJECT_ID.pattern)]


def parse_project_id(raw: str) -> ProjectId:
    if PROJECT_ID.fullmatch(raw) is None:
        raise UnknownProject(f"a project id is p- or pb- and 16 lowercase hex digits, not {raw!r}")
    return ProjectId(raw)


def new_project_id() -> ProjectId:
    return ProjectId(f"p-{secrets.token_hex(8)}")


def legacy_project(brief_id: BriefId) -> ProjectId:
    return ProjectId(f"{LEGACY}{brief_id}")
