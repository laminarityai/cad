"""A model that replays a JSON script, for tests, evals and live lanes that need no API key.

```json
{"steps": [
  {"text": "I will build it.", "calls": [{"name": "create_brief"}]},
  {"calls": [{"name": "propose_requirements", "input": {"brief_id": "${create_brief.brief_id}"}}]},
  {"text": "Done."}
]}
```

Step n answers the nth assistant message of the conversation, so the double holds no state and a
restarted server picks up where the transcript is. A step with no calls ends the turn. In a call's
input, a string that is exactly `${tool.path}` becomes that value from the latest result of `tool`
(a dotted path, with list indexes as numbers), `${tool.path}` inside a longer string becomes its
text, and a string that starts with `@file:` becomes the contents of that file, relative to the
script.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from pydantic import Field

from cad.chat.model import Message, ModelUnavailable, Text, ToolResult, ToolSpec, ToolUse
from cad.frozen import Frozen

REFERENCE: Final = re.compile(r"\$\{([A-Za-z0-9_]+)\.([^}]+)\}")
FILE_PREFIX: Final = "@file:"
EXHAUSTED: Final = "The script has no more steps."


class Call(Frozen):
    name: str
    input: dict[str, Any] = Field(default_factory=dict[str, Any])


class Step(Frozen):
    text: str = ""
    calls: tuple[Call, ...] = ()


class Script(Frozen):
    steps: tuple[Step, ...]


@dataclass(frozen=True, slots=True)
class Scripted:
    script: Script
    directory: Path

    @staticmethod
    def load(path: str) -> "Scripted":
        file = Path(path).expanduser().resolve()
        return Scripted(Script.model_validate_json(file.read_text()), file.parent)

    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message:
        del system, tools
        index = sum(one.role == "assistant" for one in messages)
        if index >= len(self.script.steps):
            return Message(role="assistant", blocks=(Text(text=EXHAUSTED),))
        step = self.script.steps[index]
        latest = _latest_results(messages)
        blocks: list[Text | ToolUse] = [Text(text=step.text)] if step.text else []
        for number, call in enumerate(step.calls):
            arguments = _resolve(call.input, latest, self.directory, index)
            blocks.append(
                ToolUse(
                    id=f"script_{index}_{number}",
                    name=call.name,
                    input=cast("dict[str, Any]", arguments),
                )
            )
        return Message(role="assistant", blocks=tuple(blocks))


def _latest_results(messages: Sequence[Message]) -> dict[str, Any]:
    names: dict[str, str] = {}
    latest: dict[str, Any] = {}
    for message in messages:
        for block in message.blocks:
            if isinstance(block, ToolUse):
                names[block.id] = block.name
            elif isinstance(block, ToolResult) and block.call_id in names:
                try:
                    latest[names[block.call_id]] = json.loads(block.text)
                except ValueError:
                    latest[names[block.call_id]] = block.text
    return latest


def _resolve(value: object, latest: dict[str, Any], directory: Path, step: int) -> object:
    if isinstance(value, dict):
        return {
            str(k): _resolve(v, latest, directory, step)
            for k, v in cast("dict[object, object]", value).items()
        }
    if isinstance(value, list):
        return [_resolve(one, latest, directory, step) for one in cast("list[object]", value)]
    if not isinstance(value, str):
        return value
    if value.startswith(FILE_PREFIX):
        return (directory / value.removeprefix(FILE_PREFIX)).read_text()
    whole = REFERENCE.fullmatch(value)
    if whole is not None:
        return _lookup(latest, whole, step)
    return REFERENCE.sub(lambda found: str(_lookup(latest, found, step)), value)


def _lookup(latest: dict[str, Any], found: re.Match[str], step: int) -> object:
    tool, path = found.group(1), found.group(2)
    held: object = latest.get(tool)
    for part in path.split("."):
        if isinstance(held, dict) and part in held:
            held = cast("dict[str, object]", held)[part]
            continue
        if isinstance(held, list) and part.isdigit():
            items = cast("list[object]", held)
            if int(part) < len(items):
                held = items[int(part)]
                continue
        raise ModelUnavailable(
            f"script step {step} refers to ${{{tool}.{path}}}, which no earlier result holds"
        )
    return held
