import logging
from pathlib import Path

from cad.briefs import store
from cad.briefs.model import Brief, BriefId
from cad.projects.model import (
    LEGACY,
    NewProjectId,
    ProjectId,
    UnknownProject,
    new_project_id,
    parse_project_id,
)

LOG = logging.getLogger(__name__)


def project_briefs(briefs: Path, project: ProjectId) -> tuple[BriefId, ...]:
    members: list[Brief] = []
    for brief_id in store.stored_briefs(briefs):
        try:
            brief = store.read_state(briefs, brief_id).brief
        except store.TamperedBrief:
            LOG.warning("brief %s is unreadable, so project %s leaves it out", brief_id, project)
            continue
        if brief.project == project:
            members.append(brief)
    return tuple(b.id for b in sorted(members, key=lambda b: b.created_at))


def project_for_new_brief(briefs: Path, raw: str | None) -> NewProjectId:
    if raw is None:
        return new_project_id()
    project = parse_project_id(raw)
    if project.startswith(LEGACY):
        raise UnknownProject(
            f"project {project} holds only the brief stored before projects existed; "
            "omit project_id to start a new project"
        )
    if not project_briefs(briefs, project):
        raise UnknownProject(
            f"no project {project} is stored; omit project_id to start a new project"
        )
    return NewProjectId(project)
