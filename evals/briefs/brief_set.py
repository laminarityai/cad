from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml


@dataclass(frozen=True, slots=True)
class BriefInput:
    id: str
    domain: str
    text: str
    grader: Mapping[str, Any] = field(default_factory=dict[str, Any])


def load_set(directory: Path) -> tuple[list[BriefInput], list[str]]:
    briefs: list[BriefInput] = []
    skipped: list[str] = []
    for path in sorted(directory.glob("*.yaml")):
        loaded: Any = yaml.safe_load(path.read_text())
        if not isinstance(loaded, dict) or not {"id", "domain", "brief"} <= loaded.keys():
            skipped.append(path.name)
            continue
        fields = cast(dict[str, Any], loaded)
        grader = fields.get("grader")
        found = BriefInput(
            str(fields["id"]),
            str(fields["domain"]),
            str(fields["brief"]).strip(),
            cast(dict[str, Any], grader) if isinstance(grader, dict) else {},
        )
        if found.id != path.stem:
            raise ValueError(f"{path.name} holds brief {found.id}: name the file <id>.yaml")
        briefs.append(found)
    return briefs, skipped


def prompt_for(brief: BriefInput) -> str:
    return f"Design this for me with the cad tools, then tell me where it stands.\n\n{brief.text}"
