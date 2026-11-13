"""What each frozen check's geometry code measured on each stored shape, plain and turned.

One signed record per check version and shape, at `projects/<pid>/agent_check_runs/<n>`, so a
card read later shows the verdict score_variant reached without running agent code again, and
scoring the same shape twice gives the same card. A new version runs the code again.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from cad.agent_checks.model import NamedValue
from cad.agent_checks.store import CheckRefused
from cad.frozen import Frozen
from cad.projects.model import ProjectBusy, ProjectId
from cad.records import signed
from cad.records.roots import project_store

RUNS: Final = "agent_check_runs"
LOG = logging.getLogger(__name__)


class GeometryRun(Frozen):
    """`values` holds what both runs agreed on, and `reason` says why there is none."""

    check_sha256: str
    version: str
    brep_sha256: str
    values: tuple[NamedValue, ...]
    reason: str | None


def read(projects: Path, project: ProjectId, version: str, brep_sha256: str) -> GeometryRun | None:
    return next(
        (
            one
            for one in _all(projects, project)
            if one.version == version and one.brep_sha256 == brep_sha256
        ),
        None,
    )


def keep(projects: Path, project: ProjectId, run: GeometryRun) -> GeometryRun:
    """The run stored for its version and shape: the first one, when two scores raced."""
    directory = projects / project / RUNS
    held: list[GeometryRun] = []

    def record_for(existing: tuple[bytes, ...]) -> bytes | None:
        held.clear()
        held.extend(
            one
            for one in _parsed(existing)
            if one.version == run.version and one.brep_sha256 == run.brep_sha256
        )
        return None if held else run.model_dump_json().encode()

    try:
        signed.append(project_store(projects), directory, _slot_of(project), record_for)
    except signed.Tampered as error:
        raise CheckRefused(_unreadable(project)) from error
    except signed.Contended as error:
        raise ProjectBusy(f"project {project} is storing a check run concurrently") from error
    return held[0] if held else run


def _all(projects: Path, project: ProjectId) -> tuple[GeometryRun, ...]:
    directory = projects / project / RUNS
    raw = signed.read_numbered(project_store(projects), directory, _slot_of(project))
    if raw is None:
        LOG.error("%s holds a record this store did not sign or cannot read", directory)
        raise CheckRefused(_unreadable(project))
    return _parsed(raw)


def _parsed(raw: tuple[bytes, ...]) -> tuple[GeometryRun, ...]:
    try:
        return tuple(GeometryRun.model_validate_json(one) for one in raw)
    except ValidationError as error:
        raise signed.Tampered from error


def _unreadable(project: ProjectId) -> str:
    return (
        f"project {project}'s agent-written check runs cannot be read; the operator must delete "
        "the project's agent_check_runs directory"
    )


def _slot_of(project: ProjectId) -> Callable[[int], str]:
    return lambda number: f"{project}/agent_check_run/{number}"
