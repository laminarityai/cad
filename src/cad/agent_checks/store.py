"""The project's frozen agent-written checks: one signed, numbered record each, never edited.

They live at `projects/<pid>/agent_checks/<n>`, signed with the project store's key like the
research ledger, so a record the agent forged or changed is refused when it is read.
"""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from cad.agent_checks.model import MAX_CHECKS_PER_BRIEF, AgentCheck
from cad.errors import Refused
from cad.projects.model import ProjectBusy, ProjectId
from cad.records import signed
from cad.records.roots import project_store

AGENT_CHECKS: Final = "agent_checks"
_OPERATOR: Final = "the operator must delete the project's agent_checks directory"
LOG = logging.getLogger(__name__)


class CheckRefused(Refused):
    """Agent-facing: why write_check stored nothing, or why a requirement cannot name a check."""


@dataclass(frozen=True, slots=True)
class StoredCheck:
    number: int
    sha256: str
    check: AgentCheck


def checks_of(projects: Path, project: ProjectId) -> tuple[StoredCheck, ...]:
    """Every frozen check of the project, in the order they were written."""
    directory = projects / project / AGENT_CHECKS
    raw = signed.read_numbered(project_store(projects), directory, _slot_of(project))
    found = None if raw is None else _parse_all(raw, project)
    if found is None:
        LOG.error("%s holds a record this store did not sign or cannot read", directory)
        raise CheckRefused(f"project {project}'s agent-written checks cannot be read; {_OPERATOR}")
    return found


def find(projects: Path, project: ProjectId, sha256: str) -> StoredCheck | None:
    return next((one for one in checks_of(projects, project) if one.sha256 == sha256), None)


def freeze(projects: Path, check: AgentCheck, still_blind: Callable[[], str | None]) -> StoredCheck:
    """Append the record unless `still_blind` names a reason not to, read once more as the slot
    is taken, or the brief already holds its limit of checks."""
    project = ProjectId(check.project)
    directory = projects / project / AGENT_CHECKS
    record = check.model_dump_json().encode()
    refused: list[str] = []

    def record_for(existing: tuple[bytes, ...]) -> bytes | None:
        refused.clear()
        held = _parse_all(existing, project)
        if held is None:
            raise signed.Tampered
        reason = still_blind() or over_the_limit(held, check.brief_id)
        if reason is not None:
            refused.append(reason)
            return None
        return record

    try:
        stored = signed.append(project_store(projects), directory, _slot_of(project), record_for)
    except signed.Tampered as error:
        raise CheckRefused(
            f"project {project}'s agent-written checks cannot be read; {_OPERATOR}"
        ) from error
    except signed.Contended as error:
        raise ProjectBusy(
            f"project {project} is storing a check concurrently; try again"
        ) from error
    if not isinstance(stored, signed.Appended):
        raise CheckRefused(refused[0] if refused else "the check was not stored")
    return StoredCheck(stored.number, hashlib.sha256(record).hexdigest(), check)


def check_ref_slot(project: ProjectId, number: int) -> str:
    return f"{project}/agent_check/{number}"


def over_the_limit(held: tuple[StoredCheck, ...], brief_id: str) -> str | None:
    if sum(1 for one in held if one.check.brief_id == brief_id) < MAX_CHECKS_PER_BRIEF:
        return None
    return f"brief {brief_id} already has {MAX_CHECKS_PER_BRIEF} agent-written checks, the most"


def _parse_all(raw: tuple[bytes, ...], project: ProjectId) -> tuple[StoredCheck, ...] | None:
    try:
        found = tuple(
            StoredCheck(
                number, hashlib.sha256(one).hexdigest(), AgentCheck.model_validate_json(one)
            )
            for number, one in enumerate(raw, start=1)
        )
    except ValidationError:
        return None
    return None if any(one.check.project != project for one in found) else found


def _slot_of(project: ProjectId) -> Callable[[int], str]:
    return lambda number: check_ref_slot(project, number)
