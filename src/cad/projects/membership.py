import logging
from pathlib import Path

from cad.briefs import store
from cad.briefs.model import BriefId
from cad.projects.model import LEGACY, ProjectId, UnknownProject, new_project_id, parse_project_id

LOG = logging.getLogger(__name__)


def project_briefs(briefs: Path, project: ProjectId) -> tuple[BriefId, ...]:
    members: list[store.BriefState] = []
    for brief_id in store.stored_briefs(briefs):
        try:
            if store.project_of(briefs, brief_id) == project:
                members.append(store.read_state(briefs, brief_id))
        except store.TamperedBrief:
            LOG.warning("brief %s is unreadable, so project %s leaves it out", brief_id, project)
    return tuple(m.brief.id for m in sorted(members, key=lambda m: m.brief.created_at))


def project_for_new_brief(briefs: Path, raw: str | None) -> ProjectId:
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
    return project
