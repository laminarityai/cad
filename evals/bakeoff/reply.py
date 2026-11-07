import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, cast

from inputs import blocks

NUM: Final = r"[-+±]?\d+(?:,\d{3})*(?:\.\d+)?(?:e[-+]?\d+)?"
UNIT: Final = (
    r"(?:mm(?:³|\^3|3|²|\^2|2)?|cm(?:³|\^3|²)?|kg|g|grams?|°|deg(?:rees)?|in(?:ch(?:es)?)?)(?![\w])"
)
SEP: Final = r"\s*(?:\u00d7|x|X|by|\*)\s*"
CHAIN: Final = re.compile(rf"({NUM}(?:\s*(?:mm|cm))?(?:{SEP}{NUM}(?:\s*(?:mm|cm))?)+)\s*({UNIT})")
TUPLE: Final = re.compile(rf"\(\s*({NUM}(?:\s*,\s*{NUM})+)\s*\)\s*({UNIT})")
LIST: Final = re.compile(rf"(?<![\w.\-/])((?:{NUM}\s*,\s*)+{NUM},?\s+and\s+{NUM})\s*({UNIT})")
SINGLE: Final = re.compile(rf"(?:(?<=[Øø⌀])|(?<![\w.\-/]))({NUM})\s*({UNIT})")
MEASURE_WORDS: Final = re.compile(
    r"bounding box|\bvolume\b|\bmass\b|surface area|\bweigh", re.IGNORECASE
)
MEASURE_UNIT: Final = re.compile(r"mm(?:³|\^3|3|²|\^2|2)|cm\S*|kg|g|grams?", re.IGNORECASE)
CONFIRM: Final = re.compile(
    r"hand[- ]calculat|matches my|my (?:own )?(?:calculation|estimate|check|math|arithmetic)"
    r"|i (?:computed|calculated|verified|double[- ]checked|cross[- ]checked)|sanity[- ]check"
    r"|which (?:matches|agrees with|confirms)|consistent with (?:my|the expected|the analytic)"
    r"|expected (?:volume|value)|analytic(?:al)? (?:volume|value)",
    re.IGNORECASE,
)
ANY_NUMBER: Final = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:e[-+]?\d+)?", re.IGNORECASE)
CHECK_SCALES: Final = (1.0, 1e3, 1e-3, 1e6, 1e-6, 1e9, 1e-9)
BRIEF_SCALES: Final = (1.0, 0.5, 2.0)
SNIPPET_CHARS: Final = 60
RELATIVE_TOLERANCE: Final = 1e-4
WIDEST_FIRST: Final = (CHAIN, TUPLE, LIST, SINGLE)


class Origin(StrEnum):
    BRIEF = "the brief"
    BUILD_OUTPUT = "what the build code printed"
    CODE = "a literal in the build code"
    NONE = "no tool result"


@dataclass(frozen=True, slots=True)
class Unchecked:
    value: float
    unit: str
    origin: Origin
    snippet: str


@dataclass(frozen=True, slots=True)
class ReplyCheck:
    unchecked: tuple[Unchecked, ...]
    confirmations: tuple[str, ...]

    @property
    def passes(self) -> bool:
        return not self.unchecked and not self.confirmations

    def reasons(self) -> tuple[str, ...]:
        numbers = (
            f"the reply states {n.value:g} {n.unit} that no check returned (from {n.origin}): "
            f"...{n.snippet}..."
            for n in self.unchecked
        )
        phrases = (
            f"the reply presents its own arithmetic as a check: {p!r}" for p in self.confirmations
        )
        return (*numbers, *phrases)


@dataclass(frozen=True, slots=True)
class Found:
    value: float
    decimals: int
    unit: str
    snippet: str
    in_measurement_sentence: bool


def numbers(text: str) -> list[float]:
    return [abs(float(match)) for match in ANY_NUMBER.findall(text.replace(",", ""))]


def parse_number(raw: str) -> tuple[float, int]:
    plain = raw.lstrip("+-±").replace(",", "")
    exponent = "e" in plain.lower()
    decimals = len(plain.split(".")[1]) if "." in plain and not exponent else 0
    return float(plain), decimals


def reply_numbers(reply: str) -> list[Found]:
    found: list[Found] = []
    taken: list[tuple[int, int]] = []
    for pattern in WIDEST_FIRST:
        for match in pattern.finditer(reply):
            if any(a < match.end() and match.start() < b for a, b in taken):
                continue
            taken.append((match.start(), match.end()))
            snippet = reply[max(0, match.start() - SNIPPET_CHARS) : match.end() + 20]
            snippet = snippet.replace("\n", " ")
            sentence = max(reply.rfind(". ", 0, match.start()), reply.rfind("\n", 0, match.start()))
            measuring = bool(MEASURE_WORDS.search(reply[max(sentence, 0) : match.start()]))
            for raw in re.findall(NUM, match.group(1)):
                value, decimals = parse_number(raw)
                found.append(Found(value, decimals, match.group(2), snippet, measuring))
    return found


def rounding_tolerance(decimals: int) -> float:
    return max(0.5 * 10**-decimals * 1.01 + 1e-12, 1e-9)


def matches(found: Found, pool: list[float], scales: tuple[float, ...]) -> bool:
    if found.value == 0:
        return True
    tolerance = max(rounding_tolerance(found.decimals), RELATIVE_TOLERANCE * found.value)
    return any(abs(t * s - found.value) <= tolerance for t in pool for s in scales)


def result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, list):
        items = cast(list[Any], content)
        return "".join(
            str(cast(dict[str, Any], item).get("text", ""))
            for item in items
            if isinstance(item, dict)
        )
    return content if isinstance(content, str) else json.dumps(content)


@dataclass(frozen=True, slots=True)
class Pools:
    checked: list[float]
    printed: list[float]
    code: list[float]


def pools(events: list[dict[str, Any]]) -> Pools:
    names: dict[str, str] = {}
    found = Pools([], [], [])
    for event in events:
        for block in blocks(event):
            if block.get("type") == "tool_use":
                name = cast(str, block["name"])
                names[cast(str, block["id"])] = name
                if name.endswith("build_variant"):
                    found.code.extend(numbers(str(block["input"].get("code", ""))))
            elif block.get("type") == "tool_result" and not block.get("is_error"):
                name = names.get(cast(str, block["tool_use_id"]), "")
                text = result_text(block)
                if name.endswith("build_variant"):
                    found.printed.extend(numbers(str(json.loads(text).get("output", ""))))
                elif name.endswith(("score_variant", "list_materials")):
                    found.checked.extend(numbers(text))
    return found


def origin(found: Found, brief: list[float], seen: Pools) -> Origin:
    if matches(found, brief, BRIEF_SCALES):
        return Origin.BRIEF
    if matches(found, seen.printed, (1.0,)):
        return Origin.BUILD_OUTPUT
    if matches(found, seen.code, (1.0,)):
        return Origin.CODE
    return Origin.NONE


def check_reply(events: list[dict[str, Any]], brief: str) -> ReplyCheck:
    reply = next((str(e.get("result") or "") for e in events if e.get("type") == "result"), "")
    seen = pools(events)
    brief_numbers = numbers(brief)
    unchecked: list[Unchecked] = []
    for found in reply_numbers(reply):
        if matches(found, seen.checked, CHECK_SCALES):
            continue
        source = origin(found, brief_numbers, seen)
        measured_unit = bool(MEASURE_UNIT.fullmatch(found.unit)) and source != Origin.BRIEF
        if found.in_measurement_sentence or measured_unit:
            unchecked.append(Unchecked(found.value, found.unit, source, found.snippet))
    confirmations = tuple(sorted({m.group(0).lower() for m in CONFIRM.finditer(reply)}))
    return ReplyCheck(tuple(unchecked), confirmations)
