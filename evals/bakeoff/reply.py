"""Report what each saved agent reply states about geometry, and where each number came from.

Run it over saved transcripts, such as the tests/evals/replies fixtures or the files that
`agree.py --out DIR` writes:

    uv run python evals/bakeoff/reply.py tests/evals/replies

For each reply it lists the numbers that match a score_variant result, the numbers no check
returned (with or without a "not checked" label), and the phrases that present the agent's own
arithmetic as confirmation. It always exits 0. It is a measurement, not a gate.

It matches phrases and units, so it misses paraphrases such as "you're good to go" and units it
does not read. The rule the server sends to every client (RULE in cad.server.app) is what
enforces the behaviour.
"""

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, cast

import pint
import yaml
from inputs import blocks
from pydantic import TypeAdapter

from cad.checks.result import CheckResult
from cad.tables.materials import UNITS, magnitude

PROMPTS: Final = Path(__file__).resolve().parent / "prompts.yaml"
RESULTS: Final = TypeAdapter(tuple[CheckResult, ...])

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
    CHECK = "a score_variant result"
    BRIEF = "the brief"
    BUILD_OUTPUT = "what the build code printed"
    CODE = "a literal in the build code"
    NONE = "no tool result"


@dataclass(frozen=True, slots=True)
class Stated:
    value: float
    unit: str
    origin: Origin
    labelled_unchecked: bool
    snippet: str


@dataclass(frozen=True, slots=True)
class Findings:
    numbers: tuple[Stated, ...]
    confirmations: tuple[str, ...]

    @property
    def checked(self) -> tuple[Stated, ...]:
        return tuple(n for n in self.numbers if n.origin == Origin.CHECK)

    @property
    def unchecked(self) -> tuple[Stated, ...]:
        return tuple(n for n in self.numbers if n.origin != Origin.CHECK)


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
    in_reply_unit = (magnitude(v, str(stated.units)) for v in same_kind)
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
                    found.checked.extend(checked_quantities(json.loads(text)["results"]))
    return found


def checked_quantities(raw: object) -> list[pint.Quantity]:
    results = RESULTS.validate_python(raw)
    values = [
        abs(m.value) for result in results for m in result.measured if not m.value.dimensionless
    ]
    thresholds = (
        quantity(parse_number(match.group(1))[0], match.group(2))
        for result in results
        for match in SINGLE.finditer(result.formula)
    )
    return [*values, *thresholds]


def origin(found: Found, brief: list[float], seen: Pools) -> Origin:
    if checked_by(found, seen.checked):
        return Origin.CHECK
    if matches(found, brief, BRIEF_SCALES):
        return Origin.BRIEF
    if matches(found, seen.printed, (1.0,)):
        return Origin.BUILD_OUTPUT
    if matches(found, seen.code, (1.0,)):
        return Origin.CODE
    return Origin.NONE


def findings(events: list[dict[str, Any]], brief: str) -> Findings:
    reply = next((str(e.get("result") or "") for e in events if e.get("type") == "result"), "")
    seen = pools(events)
    brief_numbers = numbers(brief)
    stated: list[Stated] = []
    for found in reply_numbers(reply):
        source = origin(found, brief_numbers, seen)
        measured_unit = bool(MEASURE_UNIT.fullmatch(found.unit)) and source != Origin.BRIEF
        if source == Origin.CHECK or found.in_measurement_sentence or measured_unit:
            stated.append(
                Stated(found.value, found.unit, source, found.labelled_unchecked, found.snippet)
            )
    self_computed = (
        m for m in SELF_COMPUTED.finditer(reply) if not labelled_unchecked(reply, *m.span())
    )
    confirmations = {m.group(0).lower() for m in (*CONFIRM.finditer(reply), *self_computed)}
    return Findings(tuple(stated), tuple(sorted(confirmations)))


def part_of(transcript: Path, parts: Sequence[str]) -> str | None:
    named = (p for p in parts if transcript.stem == p or transcript.stem.startswith(f"{p}_"))
    return max(named, key=len, default=None)


def report(name: str, part: str | None, found: Findings) -> str:
    def line(n: Stated) -> str:
        return f"    {n.value:g} {n.unit} from {n.origin}: ...{n.snippet}..."

    checked = ", ".join(f"{n.value:g} {n.unit}" for n in found.checked) or "none"
    labelled = [line(n) for n in found.unchecked if n.labelled_unchecked]
    unlabelled = [line(n) for n in found.unchecked if not n.labelled_unchecked]
    return "\n".join(
        [
            f"{name} (brief: {part or 'none matched'})",
            f"  checked numbers: {checked}",
            f"  numbers no check returned, labelled as not checked: {len(labelled)}",
            *labelled,
            f"  numbers no check returned, unlabelled: {len(unlabelled)}",
            *unlabelled,
            f"  confirmation phrases: {', '.join(map(repr, found.confirmations)) or 'none'}",
        ]
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="transcript files or directories")
    args = parser.parse_args(argv)
    briefs = {row["id"]: row["prompt"] for row in yaml.safe_load(PROMPTS.read_text())}
    paths = cast(list[Path], args.paths)
    transcripts = sorted(f for p in paths for f in (p.glob("*.json") if p.is_dir() else [p]))
    for transcript in transcripts:
        part = part_of(transcript, list(briefs))
        events = cast(list[dict[str, Any]], json.loads(transcript.read_text()))
        print(report(transcript.name, part, findings(events, briefs.get(part or "", ""))))


if __name__ == "__main__":
    main()
