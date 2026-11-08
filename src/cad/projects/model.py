"""What a project id is, and the record by which a brief names the project it was born in."""

import re
import secrets
from typing import Annotated, Final, NewType

from pydantic import BaseModel, ConfigDict, StringConstraints

from cad.briefs.model import BriefId

ProjectId = NewType("ProjectId", str)
PROJECT_ID: Final = re.compile(r"(p|pb)-[0-9a-f]{16}")
DERIVED: Final = "pb-"


class ProjectRefused(Exception):
    """Agent-facing. The message names the project id, never a host path."""


class UnknownProject(ProjectRefused):
    pass


class Membership(BaseModel):
    """`<brief_id>/project.signed`: written with the brief, in the same rename, and never again."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: Annotated[ProjectId, StringConstraints(pattern=PROJECT_ID.pattern)]


def parse_project_id(raw: str) -> ProjectId:
    if PROJECT_ID.fullmatch(raw) is None:
        raise UnknownProject(f"a project id is p- or pb- and 16 lowercase hex digits, not {raw!r}")
    return ProjectId(raw)


def new_project_id() -> ProjectId:
    return ProjectId(f"p-{secrets.token_hex(8)}")


def derived_project(brief_id: BriefId) -> ProjectId:
    """The project of a brief stored before projects existed: it holds that brief and no other."""
    return ProjectId(f"{DERIVED}{brief_id}")
