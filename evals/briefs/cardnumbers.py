"""Every quantity and every bare int or float in dumped scorecard data, with where it sits."""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

type Where = tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class Found:
    where: Where
    value: str


def numbers_in(data: object, where: Where = ()) -> Iterator[Found]:
    """Every quantity and every bare int or float in dumped card data, with where it sits."""
    if isinstance(data, Mapping):
        fields = cast(Mapping[str, object], data)
        magnitude = fields.get("magnitude")
        if set(fields) == {"magnitude", "unit"} and isinstance(magnitude, int | float):
            yield Found(where, f"{magnitude:g} {fields['unit']}")
            return
        for name, item in fields.items():
            yield from numbers_in(item, (*where, name))
    elif isinstance(data, list | tuple):
        for index, item in enumerate(cast(Sequence[object], data)):
            yield from numbers_in(item, (*where, index))
    elif isinstance(data, int | float) and not isinstance(data, bool):
        yield Found(where, f"{data:g}")


def path_of(where: Where) -> str:
    return "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in where)[1:]
