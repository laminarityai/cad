"""The page's snapshot: the items it showed, sealed for one session and one project.

The form carries `<base64url of the items JSON>.<mac>`. The projects key signs it under the
slot `<project>/page`, apart from the answer slots `<project>/answer/<n>`, over the account,
the session and the items. Nothing is kept in memory, so it survives a restart, and another
account's key or another session cannot open it.
"""

import base64
import binascii
import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from cad.accounts.principal import PersonSession
from cad.confirmations.answers import ItemRef
from cad.projects.model import ProjectId
from cad.variants import key

ITEMS: TypeAdapter[tuple[ItemRef, ...]] = TypeAdapter(tuple[ItemRef, ...])


def seal(
    projects: Path, person: PersonSession, project: ProjectId, items: tuple[ItemRef, ...]
) -> str:
    shown = ITEMS.dump_json(items).decode()
    payload = base64.urlsafe_b64encode(shown.encode()).decode().rstrip("=")
    return f"{payload}.{key.sign(projects, _slot(project), _bound(person, shown)).decode()}"


def unseal(
    projects: Path, person: PersonSession, project: ProjectId, sealed: str
) -> tuple[ItemRef, ...] | None:
    payload, dot, mac = sealed.partition(".")
    if not dot or not payload.isascii() or not mac.isascii():
        return None
    try:
        shown = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if not key.verify(projects, _slot(project), _bound(person, shown), mac.encode()):
        return None
    try:
        return ITEMS.validate_json(shown)
    except ValidationError:
        return None


def _slot(project: ProjectId) -> str:
    return f"{project}/page"


def _bound(person: PersonSession, shown: str) -> bytes:
    return json.dumps([person.account, person.session_id, shown]).encode()
