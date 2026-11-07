import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

ATTEMPTS: Final = Path(__file__).resolve().parent / "runs" / "build123d"
FILE_PATTERN: Final = re.compile(r"attempt(\d+)\.py")


@dataclass(frozen=True, slots=True)
class Attempt:
    model: str
    part: str
    sample: str
    path: Path

    @property
    def label(self) -> str:
        return f"{self.model}/{self.part}/{self.sample}"


def stored_attempts(number: int | None) -> list[Attempt]:
    """The final attempt of each stored run, or attempt `number` of the runs that have it."""
    found: list[Attempt] = []
    for sample in sorted(ATTEMPTS.glob("*/*/*")):
        files = {
            int(match[1]): path
            for path in sample.glob("attempt*.py")
            if (match := FILE_PATTERN.fullmatch(path.name))
        }
        chosen = max(files, default=None) if number is None else number
        if chosen in files:
            found.append(
                Attempt(sample.parts[-3], sample.parts[-2], sample.parts[-1], files[chosen])
            )
    return found


def as_result_contract(code: str) -> str:
    """The bake-off scripts end with `export_step(shape, "out.step")`. The server reads `result`."""
    for node in reversed(ast.parse(code).body):
        call = node.value if isinstance(node, ast.Expr) else None
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "export_step"
            and len(call.args) == 2
            and isinstance(call.args[1], ast.Constant)
            and call.args[1].value == "out.step"
            and node.end_lineno is not None
        ):
            lines = code.splitlines(keepends=True)
            shape = ast.get_source_segment(code, call.args[0])
            before, after = lines[: node.lineno - 1], lines[node.end_lineno :]
            return "".join(before) + f"result = {shape}\n" + "".join(after)
    raise ValueError('the script has no top-level export_step(shape, "out.step")')


def brief_prompt(brief: str, material_key: str) -> str:
    return (
        "Build this part with the build_variant tool, then score the variant with the "
        f"score_variant tool using material_key {material_key}. If the build fails, fix the "
        "code and build again. Report the scorecard's verdicts exactly as score_variant "
        f"returns them.\n\nBrief: {brief}"
    )


@dataclass(frozen=True, slots=True)
class Session:
    scored_variant: str | None
    cost_usd: float | None
    tool_calls: tuple[str, ...]


def blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    message = cast(dict[str, Any], event.get("message", {}))
    content = message.get("content")
    return cast(list[dict[str, Any]], content) if isinstance(content, list) else []


def read_session(events: list[dict[str, Any]]) -> Session:
    """The variant of the last score_variant call that did not return an error."""
    asked: dict[str, str] = {}
    scored: str | None = None
    calls: list[str] = []
    cost: float | None = None
    for event in events:
        if event.get("type") == "result":
            cost = cast(float | None, event.get("total_cost_usd"))
        for block in blocks(event):
            if block.get("type") == "tool_use":
                name = cast(str, block["name"])
                calls.append(name)
                if name == "mcp__cad__score_variant":
                    asked[cast(str, block["id"])] = cast(str, block["input"].get("variant_id", ""))
            elif block.get("type") == "tool_result" and not block.get("is_error"):
                answered = cast(str, block["tool_use_id"])
                if answered in asked:
                    scored = asked[answered]
    return Session(scored, cost, tuple(calls))
