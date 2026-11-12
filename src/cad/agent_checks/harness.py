"""The one way agent code runs against a shape: one build sandbox container, one script.

Each slot runs one snippet in a fresh namespace that holds the build123d names, its own copy of
its shape as `part`, and `report`, which prints at most `MAX_VALUES` values and counts the rest.
A shape is stored BREP bytes or build123d code that sets `probe`. With a motion, the script turns
and moves each shape before the snippet sees it, and bakes the motion into the geometry. Every
line the host reads starts with `MARK`, which holds no character that `str.splitlines` splits
on, such as `\\x1e`.

`cad.scorecard.score` must never import this package: check versions hash what it imports, and
this code can change without moving a team check version.
"""

import base64
import json
import math
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

from cad.agent_checks.model import NAME, UNITS
from cad.sandbox import host, image
from cad.sandbox.outcome import BuildFailed, Failure, NoResult, OutOfMemory, TimedOut

MARK: Final = "@@cad-measure "
MAX_VALUES: Final = 8
WALL_SECONDS: Final = 30
MAX_BREP_BYTES: Final = 32 * 2**20
TOO_LARGE: Final = "part too large to measure here"
CUT: Final = "not reported: its output was lost or cut to the last 8 KiB"

PREAMBLE: Final = """
import base64 as _base64, json as _json
from build123d import *
_NAMES = {{_k: _v for _k, _v in dict(globals()).items() if not _k.startswith("_")}}

def _say(**fields):
    print("\\n" + {mark!r} + _json.dumps(fields), flush=True)

def _reporter(slot, counts):
    def report(name, value, unit):
        if counts[0] >= {max_values}:
            counts[1] += 1
            return
        counts[0] += 1
        _say(slot=slot, name=str(name), value=float(value), unit=str(unit))
    return report

def _brep(index, data):
    path = f"/tmp/shape-{{index}}.brep"
    with open(path, "wb") as _file:
        _file.write(_base64.b64decode(data))
    return lambda: import_brep(path)

def _built(code):
    def build():
        names = dict(_NAMES)
        exec(compile(code, "<probe>", "exec"), names)
        return names["probe"]
    return build

def _turned(make, motion):
    if motion is None:
        return make
    axis, degrees, offset = motion
    return lambda: make().rotate(Axis((0, 0, 0), axis), degrees, transform=True).translate(
        offset, transform=True
    )

def _measure(slot, make, code):
    counts = [0, 0]
    try:
        part = make()
        exec(compile(code, f"<measurement {{slot}}>", "exec"),
             {{**_NAMES, "part": part, "report": _reporter(slot, counts)}})
    except BaseException as _error:
        _say(slot=slot, failed=repr(_error)[:300])
    else:
        _say(slot=slot, done=True, sent=counts[0], dropped=counts[1])
"""


@dataclass(frozen=True, slots=True)
class Brep:
    data: bytes


@dataclass(frozen=True, slots=True)
class Probe:
    """build123d code that sets `probe` to a shape."""

    code: str


type Shape = Brep | Probe


@dataclass(frozen=True, slots=True)
class Motion:
    """A rigid motion: a turn about an axis through the origin, then a move."""

    axis: tuple[float, float, float]
    degrees: float
    offset: tuple[float, float, float]

    @classmethod
    def drawn(cls) -> "Motion":
        """A motion from the operating system's randomness, which the agent cannot compute."""
        draw = secrets.SystemRandom()
        while True:
            axis = (draw.uniform(-1, 1), draw.uniform(-1, 1), draw.uniform(-1, 1))
            length = math.hypot(*axis)
            if 0.1 < length <= 1:
                break
        unit = (axis[0] / length, axis[1] / length, axis[2] / length)
        offset = (draw.uniform(-500, 500), draw.uniform(-500, 500), draw.uniform(-500, 500))
        return cls(unit, draw.uniform(20, 340), offset)


@dataclass(frozen=True, slots=True)
class Slot:
    """Run `code` on shape number `shape`."""

    code: str
    shape: int


@dataclass(frozen=True, slots=True)
class Reading:
    name: str
    value: float
    unit: str


@dataclass(frozen=True, slots=True)
class Values:
    readings: tuple[Reading, ...]
    dropped: int


@dataclass(frozen=True, slots=True)
class Failed:
    reason: str


type Outcome = Values | Failed


def run(
    shapes: Sequence[Shape], slots: Sequence[Slot], motion: Motion | None = None
) -> tuple[Outcome, ...]:
    """One outcome per slot. Raises SandboxUnavailable when no container can run."""
    if sum(len(one.data) for one in shapes if isinstance(one, Brep)) > MAX_BREP_BYTES:
        return tuple(Failed(TOO_LARGE) for _ in slots)
    tag = image.image_tag(image.BUILD)
    ran = host.build(
        compose(shapes, slots, motion), image.current_image(tag), wall_seconds=WALL_SECONDS
    )
    held = _slots(ran.output)
    unfinished = _unfinished(ran.verdict)
    return tuple(_judged(held.get(number, _Slot()), unfinished) for number in range(len(slots)))


def compose(shapes: Sequence[Shape], slots: Sequence[Slot], motion: Motion | None) -> str:
    """`result` is a point, so the build report stays tiny whatever the snippets did."""
    head = PREAMBLE.format(mark=MARK, max_values=MAX_VALUES)
    turn = None if motion is None else (motion.axis, motion.degrees, motion.offset)
    made = "".join(
        f"_SHAPES.append(_turned({_maker(number, one)}, {turn!r}))\n"
        for number, one in enumerate(shapes)
    )
    body = "".join(
        f"_measure({number}, _SHAPES[{one.shape}], {one.code!r})\n"
        for number, one in enumerate(slots)
    )
    return head + "_SHAPES = []\n" + made + body + "result = Vertex(0, 0, 0)\n"


def _maker(number: int, shape: Shape) -> str:
    match shape:
        case Brep(data=data):
            return f"_brep({number}, {base64.b64encode(data).decode()!r})"
        case Probe(code=code):
            return f"_built({code!r})"


@dataclass
class _Slot:
    values: list[Mapping[str, object]] = field(default_factory=list[Mapping[str, object]])
    failed: str | None = None
    done: bool = False
    sent: int = 0
    dropped: int = 0


def _slots(output: str) -> dict[int, _Slot]:
    slots: dict[int, _Slot] = {}
    for line in output.splitlines():
        if not line.startswith(MARK):
            continue
        try:
            raw = json.loads(line[len(MARK) :])
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        fields = cast(Mapping[str, object], raw)
        slot = fields.get("slot")
        if not isinstance(slot, int) or isinstance(slot, bool):
            continue
        held = slots.setdefault(slot, _Slot())
        if "failed" in fields:
            held.failed = str(fields["failed"])[:300]
        elif fields.get("done") is True:
            held.done = True
            held.sent, held.dropped = _count(fields, "sent"), _count(fields, "dropped")
        else:
            held.values.append(fields)
    return slots


def _count(fields: Mapping[str, object], key: str) -> int:
    count = fields.get(key)
    return count if isinstance(count, int) and not isinstance(count, bool) else -1


def _unfinished(verdict: host.Artifacts | Failure) -> str:
    match verdict:
        case TimedOut(limit_seconds=seconds):
            return f"timed out after {seconds} s"
        case OutOfMemory():
            return "ran out of memory"
        case BuildFailed(error=error):
            return f"not reported: the measuring run failed: {error[:300]}"
        case NoResult() | host.Artifacts():
            return CUT


def _judged(slot: _Slot, unfinished: str) -> Outcome:
    if slot.failed is not None:
        return Failed(slot.failed)
    if not slot.done:
        return Failed(unfinished)
    if len(slot.values) != slot.sent:
        return Failed(CUT)
    if not slot.values:
        return Failed("the code reported no value")
    readings: list[Reading] = []
    for raw in slot.values:
        parsed = _reading(raw)
        if isinstance(parsed, str):
            return Failed(parsed)
        if any(kept.name == parsed.name for kept in readings):
            return Failed(f"value name {parsed.name} was reported twice")
        readings.append(parsed)
    return Values(tuple(readings), slot.dropped)


def _reading(raw: Mapping[str, object]) -> Reading | str:
    name, value, unit = raw.get("name"), raw.get("value"), raw.get("unit")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return f"value name {name!r} does not match {NAME.pattern}"
    if not isinstance(value, float) or not math.isfinite(value):
        return f"value {name} is {value!r}, not a finite number"
    if not isinstance(unit, str) or unit not in UNITS:
        return f"value {name} has unit {unit!r}, not one of {', '.join(UNITS)}"
    return Reading(name, value, unit)
