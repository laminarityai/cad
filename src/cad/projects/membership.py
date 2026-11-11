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
from cad.records import files
from cad.records.roots import Roots

LOG = logging.getLogger(__name__)


def _stored_briefs(roots: Roots) -> list[BriefId]:
    if not files.is_directory(roots.briefs):
        return []
    return [
        BriefId(path.name)
        for path in roots.briefs.iterdir()
        if store.ID_PATTERN.fullmatch(path.name) and files.is_directory(path)
    ]


def stored_projects(roots: Roots) -> dict[ProjectId, tuple[Brief, ...]]:
    members: dict[ProjectId, list[Brief]] = {}
    for brief_id in _stored_briefs(roots):
        try:
            brief = store.read_brief(roots, brief_id)
        except store.TamperedBrief:
            LOG.warning("brief %s is unreadable, so its project leaves it out", brief_id)
            continue
        members.setdefault(brief.project, []).append(brief)
    projects = {
        project: tuple(sorted(briefs, key=lambda b: b.created_at))
        for project, briefs in members.items()
    }
    return dict(sorted(projects.items(), key=lambda one: one[1][-1].created_at, reverse=True))


def project_briefs(roots: Roots, project: ProjectId) -> tuple[BriefId, ...]:
    return tuple(b.id for b in stored_projects(roots).get(project, ()))


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
