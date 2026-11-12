"""The one formula an agent-written check holds, in a closed arithmetic grammar the host walks.

The text is parsed with `ast` in eval mode and never reaches `exec` or `eval`: this module reads
each node, and refuses anything outside the grammar. It runs on the host, so it is deterministic.
"""

import ast
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

import pint

from cad.tables.materials import UNITS

# Part of every agent check's version: change it whenever what a formula means changes.
EVALUATOR: Final = "1"
MAX_NODES: Final = 120
MAX_EXPONENT: Final = 10
ARITY: Final[Mapping[str, int | None]] = {"sqrt": 1, "abs": 1, "min": None, "max": None}
CONSTANTS: Final[Mapping[str, float]] = {"pi": math.pi}
GRAMMAR: Final = (
    "numbers, names, + - * /, ** with a number of at most 10 as the exponent, sqrt, abs, "
    "min, max and pi"
)

type Dimension = pint.util.UnitsContainer
type Op = type[ast.operator]


@dataclass(frozen=True, slots=True)
class Formula:
    text: str
    body: ast.expr
    names: frozenset[str]


class _Unworkable(Exception):
    pass


def parse(text: str) -> Formula | str:
    """The formula, or why it is refused."""
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return f"the formula {text!r} is not one expression of {GRAMMAR}"
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        return f"the formula has more than {MAX_NODES} parts"
    names: set[str] = set()
    refused = _refused(tree.body, names)
    if refused is not None:
        return refused
    return Formula(text=text, body=tree.body, names=frozenset(names))


def evaluate(formula: Formula, values: Mapping[str, pint.Quantity]) -> pint.Quantity | str:
    """The formula's value on `values`, or why it has none, such as a division by zero."""
    try:
        return _value(formula.body, values)
    except _Unworkable as error:
        return str(error)
    except ZeroDivisionError:
        return "the formula divides by zero"
    except OverflowError:
        return "the formula's value is too large"
    except pint.PintError as error:
        return f"the formula's units do not agree: {error}"


def dimension(formula: Formula, dimensions: Mapping[str, Dimension]) -> Dimension | str:
    """The dimension of the formula's value, or the first place two dimensions disagree. Every
    sum, min and max must hold one dimension, and so must the arguments of each."""
    try:
        return _dimension(formula.body, dimensions)
    except _Unworkable as error:
        return str(error)


def dimension_of(unit: str) -> Dimension:
    return UNITS.Quantity(1, unit).dimensionality


def _refused(node: ast.expr, names: set[str]) -> str | None:
    match node:
        case ast.Constant(value=value) if type(value) in (int, float):
            return None
        case ast.Name(id=name) if name in ARITY:
            return f"{name} must be called, as in {name}(x)"
        case ast.Name(id=name):
            if name not in CONSTANTS:
                names.add(name)
            return None
        case ast.BinOp(left=left, op=ast.Pow(), right=right):
            if _exponent(right) is None:
                return f"a power's exponent must be a number of at most {MAX_EXPONENT}"
            return _refused(left, names)
        case ast.BinOp(left=left, op=ast.Add() | ast.Sub() | ast.Mult() | ast.Div(), right=right):
            return _refused(left, names) or _refused(right, names)
        case ast.UnaryOp(op=ast.USub() | ast.UAdd(), operand=operand):
            return _refused(operand, names)
        case ast.Call(func=ast.Name(id=called), args=args, keywords=[]) if called in ARITY:
            wanted = ARITY[called]
            if (wanted is None and len(args) < 2) or (wanted is not None and len(args) != wanted):
                count = "two or more values" if wanted is None else "one value"
                return f"{called} takes {count}"
            return next((r for one in args if (r := _refused(one, names)) is not None), None)
        case _:
            return f"the formula may hold only {GRAMMAR}, not {ast.unparse(node)!r}"


def _exponent(node: ast.expr) -> float | None:
    match node:
        case ast.Constant(value=int() | float() as value) if type(value) is not bool:
            number = float(value)
        case ast.UnaryOp(op=ast.USub(), operand=ast.Constant(value=int() | float() as value)) if (
            type(value) is not bool
        ):
            number = -float(value)
        case _:
            return None
    return number if abs(number) <= MAX_EXPONENT else None


_ARITHMETIC: Final[Mapping[Op, Callable[[pint.Quantity, pint.Quantity], pint.Quantity]]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}


def _value(node: ast.expr, values: Mapping[str, pint.Quantity]) -> pint.Quantity:
    match node:
        case ast.Constant(value=int() | float() as value):
            found = UNITS.Quantity(float(value), "dimensionless")
        case ast.Name(id=name) if name in CONSTANTS:
            found = UNITS.Quantity(CONSTANTS[name], "dimensionless")
        case ast.Name(id=name):
            found = values[name]
        case ast.BinOp(left=left, op=ast.Pow(), right=right):
            found = _power(_value(left, values), _exponent(right) or 0.0)
        case ast.BinOp(left=left, op=op, right=right):
            found = _ARITHMETIC[type(op)](_value(left, values), _value(right, values))
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            found = -_value(operand, values)
        case ast.UnaryOp(operand=operand):
            found = _value(operand, values)
        case ast.Call(func=ast.Name(id="sqrt"), args=[one]):
            found = _power(_value(one, values), 0.5)
        case ast.Call(func=ast.Name(id="abs"), args=[one]):
            found = abs(_value(one, values))
        case ast.Call(func=ast.Name(id=called), args=args):
            found = _extreme([_value(one, values) for one in args], largest=called == "max")
        case _:
            raise _Unworkable(f"the formula may hold only {GRAMMAR}")
    if not math.isfinite(_magnitude(found)):
        raise _Unworkable(f"the formula's value at {ast.unparse(node)!r} is not a finite number")
    return found


def _power(base: pint.Quantity, exponent: float) -> pint.Quantity:
    if _magnitude(base) < 0 and not exponent.is_integer():
        raise _Unworkable("the formula takes a root of a negative number")
    return base**exponent


def _extreme(found: list[pint.Quantity], *, largest: bool) -> pint.Quantity:
    unit = found[0].units
    in_one_unit = [float(one.to(unit).magnitude) for one in found]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    chosen = max(in_one_unit) if largest else min(in_one_unit)
    return found[in_one_unit.index(chosen)]


def _magnitude(quantity: pint.Quantity) -> float:
    return float(quantity.magnitude)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _dimension(node: ast.expr, dimensions: Mapping[str, Dimension]) -> Dimension:
    match node:
        case ast.Constant() | ast.Name(id="pi"):
            return dimension_of("dimensionless")
        case ast.Name(id=name):
            return dimensions[name]
        case ast.BinOp(left=left, op=ast.Pow(), right=right):
            return _dimension(left, dimensions) ** (_exponent(right) or 0.0)
        case ast.BinOp(left=left, op=ast.Mult(), right=right):
            return _dimension(left, dimensions) * _dimension(right, dimensions)
        case ast.BinOp(left=left, op=ast.Div(), right=right):
            return _dimension(left, dimensions) / _dimension(right, dimensions)
        case ast.BinOp(left=left, right=right):
            return _same(node, [_dimension(left, dimensions), _dimension(right, dimensions)])
        case ast.UnaryOp(operand=operand):
            return _dimension(operand, dimensions)
        case ast.Call(func=ast.Name(id="sqrt"), args=[one]):
            return _dimension(one, dimensions) ** 0.5
        case ast.Call(args=args):
            return _same(node, [_dimension(one, dimensions) for one in args])
        case _:
            raise _Unworkable(f"the formula may hold only {GRAMMAR}")


def _same(node: ast.expr, found: list[Dimension]) -> Dimension:
    if any(one != found[0] for one in found):
        shown = " and ".join(str(one) or "dimensionless" for one in found)
        raise _Unworkable(f"{ast.unparse(node)!r} joins values of different kinds: {shown}")
    return found[0]
