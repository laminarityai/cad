import math

type Point = tuple[float, float, float]


def angle(a: Point, b: Point) -> float:
    return math.atan2(norm(cross(a, b)), dot(a, b))


def add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Point, k: float) -> Point:
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a: Point) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Point) -> Point:
    return scale(a, 1 / norm(a))
