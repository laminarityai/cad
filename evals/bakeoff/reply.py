import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, cast

import pint
from inputs import blocks

from cad.scorecard.model import Scorecard
from cad.tables.materials import UNITS

NUM: Final = r"[-+±]?\d+(?:,\d{3})*(?:\.\d+)?(?:e[-+]?\d+)?"
UNIT: Final = (
    r"(?:k?g/(?:mm|cm)(?:³|\^3|3)|(?:mm|cm)(?:³|\^3|3|²|\^2|2)?|kg|g|grams?|°|deg(?:rees)?"
    r"|in(?:ch(?:es)?)?)(?![\w])"
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
    r"matches my|i (?:confirmed|verified|double[- ]checked|cross[- ]checked)|sanity[- ]check"
    r"|which (?:matches|agrees with|confirms)"
    r"|consistent with (?:my|the expected|the analytic|the scorecard)"
    r"|(?:matches|agrees with|confirms) the scorecard",
    re.IGNORECASE,
)
SELF_COMPUTED: Final = re.compile(
    r"hand[- ]calculat|my (?:own )?(?:calculation|estimate|check|math|arithmetic)"
    r"|i (?:computed|calculated)|expected (?:volume|value)|analytic(?:al)? (?:volume|value)",
    re.IGNORECASE,
)
LABEL: Final = r"\bnot (?:from )?a check\b|\bnot checked\b|\bunchecked\b|\bnot measured\b"
UNCHECKED_LABEL: Final = re.compile(LABEL, re.IGNORECASE)
BARE_LABEL: Final = re.compile(
    rf"(?:(?:which|that|this|it) )?(?:is |was )?(?:{LABEL})", re.IGNORECASE
)
SENTENCE_END: Final = re.compile(r"\n|\.(?!\d)")
CLAUSE_BREAK: Final = re.compile(r"[;:,()\[\]]|\b(?:and|but|while)\b", re.IGNORECASE)
ANY_NUMBER: Final = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:e[-+]?\d+)?", re.IGNORECASE)
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
    labelled_unchecked: bool


def numbers(text: str) -> list[float]:
    return [abs(float(match)) for match in ANY_NUMBER.findall(text.replace(",", ""))]


def parse_number(raw: str) -> tuple[float, int]:
    plain = raw.lstrip("+-±").replace(",", "")
    exponent = "e" in plain.lower()
    decimals = len(plain.split(".")[1]) if "." in plain and not exponent else 0
    return float(plain), decimals


def sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    before = max((m.end() for m in SENTENCE_END.finditer(text, 0, start)), default=0)
    after = next((m.start() for m in SENTENCE_END.finditer(text, end)), len(text))
    return before, after


def clauses(text: str) -> list[tuple[int, int]]:
    edges = [0, *(i for m in CLAUSE_BREAK.finditer(text) for i in m.span()), len(text)]
    spans = zip(edges[::2], edges[1::2], strict=True)
    return [(a, b) for a, b in spans if text[a:b].strip(" *_`")]


def labelled_unchecked(text: str, start: int, end: int) -> bool:
    first, last = sentence_bounds(text, start, end)
    sentence = text[first:last]
    spans = clauses(sentence)
    hit = [i for i, (a, b) in enumerate(spans) if a < end - first and start - first < b]
    own = sentence[spans[hit[0]][0] : spans[hit[-1]][1]]
    beside = (spans[i] for i in (hit[0] - 1, hit[-1] + 1) if 0 <= i < len(spans))
    return bool(UNCHECKED_LABEL.search(own)) or any(
        BARE_LABEL.fullmatch(sentence[a:b].strip(" *_`")) for a, b in beside
    )


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
            sentence, _ = sentence_bounds(reply, match.start(), match.end())
            measuring = bool(MEASURE_WORDS.search(reply[sentence : match.start()]))
            labelled = labelled_unchecked(reply, match.start(), match.end())
            for raw in re.findall(NUM, match.group(1)):
                value, decimals = parse_number(raw)
                found.append(Found(value, decimals, match.group(2), snippet, measuring, labelled))
    return found


def rounding_tolerance(decimals: int) -> float:
    return max(0.5 * 10**-decimals * 1.01 + 1e-12, 1e-9)


def tolerance(found: Found) -> float:
    return max(rounding_tolerance(found.decimals), RELATIVE_TOLERANCE * found.value)


def matches(found: Found, pool: list[float], scales: tuple[float, ...]) -> bool:
    return any(abs(t * s - found.value) <= tolerance(found) for t in pool for s in scales)


def quantity(value: float, unit: str) -> pint.Quantity:
    return UNITS.Quantity(value, re.sub(r"(?<=m)([23])$", r"^\1", unit))


def checked_by(found: Found, checked: list[pint.Quantity]) -> bool:
    stated = quantity(found.value, found.unit)
    same_kind = (value for value in checked if value.dimensionality == stated.dimensionality)
    # Pint's annotations leave conversions partly untyped, as in cad.tables.materials.
    in_reply_unit = (float(v.m_as(stated.units)) for v in same_kind)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return any(abs(v - found.value) <= tolerance(found) for v in in_reply_unit)


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
    checked: list[pint.Quantity]
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
                elif name.endswith("score_variant"):
                    found.checked.extend(checked_quantities(Scorecard.model_validate_json(text)))
    return found


def checked_quantities(card: Scorecard) -> list[pint.Quantity]:
    values = [
        abs(m.value)
        for result in card.results
        for m in result.measured
        if not m.value.dimensionless
    ]
    thresholds = (
        quantity(parse_number(match.group(1))[0], match.group(2))
        for result in card.results
        for match in SINGLE.finditer(result.formula)
    )
    return [*values, *thresholds]


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
        if found.labelled_unchecked or checked_by(found, seen.checked):
            continue
        source = origin(found, brief_numbers, seen)
        measured_unit = bool(MEASURE_UNIT.fullmatch(found.unit)) and source != Origin.BRIEF
        if found.in_measurement_sentence or measured_unit:
            unchecked.append(Unchecked(found.value, found.unit, source, found.snippet))
    self_computed = (
        m for m in SELF_COMPUTED.finditer(reply) if not labelled_unchecked(reply, *m.span())
    )
    confirmations = {m.group(0).lower() for m in (*CONFIRM.finditer(reply), *self_computed)}
    return ReplyCheck(tuple(unchecked), tuple(sorted(confirmations)))
