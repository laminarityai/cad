"""The parts and lookups the build-into-set tests share."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from cad.variant_sets import store

if TYPE_CHECKING:
    from tests.support.variant_set_session import Session

PARTS: Final = Path(__file__).parents[1] / "sandbox/parts"
PLATE: Final = (PARTS / "plate.py").read_text()
BRACKET: Final = (PARTS / "l_bracket.py").read_text()
THICKER: Final = PLATE + "\n# a thicker wall\n"
NO_DOCKER: Final = "unix:///nonexistent/docker.sock"


def held(s: Session, brief_id: str) -> list[store.Member]:
    key = store.set_key(s.roots, brief_id)
    return list(store.members(s.tmp / "projects", key))


def shows(s: Session, brief_id: str) -> list[str]:
    return [m.latest.built_as for m in held(s, brief_id)]
