import logging

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
from cad.records.roots import Roots

LOG = logging.getLogger(__name__)


def project_briefs(roots: Roots, project: ProjectId) -> tuple[BriefId, ...]:
    members: list[Brief] = []
    for brief_id in store.stored_briefs(roots):
        try:
            brief = store.read_brief(roots, brief_id)
        except store.TamperedBrief:
            LOG.warning("brief %s is unreadable, so project %s leaves it out", brief_id, project)
            continue
        if brief.project == project:
            members.append(brief)
    return tuple(b.id for b in sorted(members, key=lambda b: b.created_at))


def project_for_new_brief(roots: Roots, raw: str | None) -> NewProjectId:
    if raw is None:
        return new_project_id()
    project = parse_project_id(raw)
    if project.startswith(LEGACY):
        raise UnknownProject(
            f"project {project} holds only the brief stored before projects existed; "
            "omit project_id to start a new project"
        )
    if not project_briefs(roots, project):
        raise UnknownProject(
            f"no project {project} is stored; omit project_id to start a new project"
        )
    return NewProjectId(project)
