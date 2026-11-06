"""Reference geometry for the assembly briefs and their starting models, in build123d.

Each starting model builds its parts where their builders put them. Each reference moves
the parts to where the brief says, in the same order.
"""

from collections.abc import Callable

from build123d import Box, Cylinder, Part, Pos, Rot

from reference import parts

Build = Callable[[], list[Part]]


def standoff() -> Part:
    return parts.tube(3, 1.6, 10)


def shaft(diameter: float, length: float) -> Part:
    return Cylinder(diameter / 2, length)


def bearing_ring() -> Part:
    return parts.tube(13.9, 5, 8)


def motor_body() -> Part:
    return Box(42, 42, 40)


STARTS: dict[str, Build] = {
    "asm_plate_standoffs": lambda: [parts.small_plate(), *[standoff() for _ in range(4)]],
    "asm_block_on_plate": lambda: [parts.plate(), parts.bearing_block()],
    "asm_shaft_in_block": lambda: [parts.bearing_block(), shaft(12, 40)],
    "asm_bearing_in_block": lambda: [parts.bearing_block(), bearing_ring()],
    "asm_gear_on_shaft": lambda: [shaft(7.9, 30), parts.spur_gear()],
    "asm_collars_on_shaft": lambda: [shaft(12.6, 50), parts.shaft_collar(), parts.shaft_collar()],
    "asm_l_bracket_on_plate": lambda: [parts.plate(), parts.l_bracket()],
    "asm_l_brackets_facing": lambda: [parts.plate(), parts.l_bracket(), parts.l_bracket()],
    "asm_arm_on_shafts": lambda: [parts.arm(), shaft(27.8, 20), shaft(27.8, 20)],
    "asm_motor_plate_on_u_bracket": lambda: [parts.u_bracket(), parts.motor_plate()],
    "asm_spacer_stack": lambda: [parts.hex_spacer() for _ in range(3)],
    "asm_pin_through_u_bracket": lambda: [parts.u_bracket(), shaft(5.8, 44)],
    "asm_gusset_in_l_bracket": lambda: [parts.l_bracket(), parts.small_gusset()],
    "asm_two_gears_on_shaft": lambda: [shaft(7.9, 30), parts.spur_gear(), parts.spur_gear()],
    "asm_blocks_on_plate": lambda: [parts.plate(), parts.bearing_block(), parts.bearing_block()],
    "asm_shaft_block_collar": lambda: [parts.bearing_block(), shaft(12.6, 50), parts.shaft_collar()],
    "asm_plates_on_standoffs": lambda: [
        parts.small_plate(),
        parts.small_plate(),
        standoff(),
        standoff(),
    ],
    "asm_box_in_u_bracket": lambda: [parts.u_bracket(), Box(30, 20, 20)],
    "asm_motor_plate_on_l_bracket": lambda: [parts.l_bracket(), parts.motor_plate()],
    "asm_motor_on_plate": lambda: [parts.motor_plate(), motor_body(), shaft(5, 24)],
}

REFERENCES: dict[str, Build] = {
    "asm_plate_standoffs": lambda: [
        parts.small_plate(),
        *[Pos(x, y, -7) * standoff() for x, y in ((25, 25), (-25, 25), (25, -25), (-25, -25))],
    ],
    "asm_block_on_plate": lambda: [parts.plate(), Pos(0, 0, 3) * parts.bearing_block()],
    "asm_shaft_in_block": lambda: [parts.bearing_block(), Pos(0, 0, 20) * shaft(12, 40)],
    "asm_bearing_in_block": lambda: [parts.bearing_block(), Pos(0, 0, 16) * bearing_ring()],
    "asm_gear_on_shaft": lambda: [shaft(7.9, 30), Pos(0, 0, -5) * parts.spur_gear()],
    "asm_collars_on_shaft": lambda: [
        shaft(12.6, 50),
        Pos(0, 0, 20) * parts.shaft_collar(),
        Pos(0, 0, -20) * parts.shaft_collar(),
    ],
    "asm_l_bracket_on_plate": lambda: [parts.plate(), Pos(-50, -15, 3) * parts.l_bracket()],
    "asm_l_brackets_facing": lambda: [
        parts.plate(),
        Pos(-50, -15, 3) * parts.l_bracket(),
        Pos(50, 15, 3) * Rot(0, 0, 180) * parts.l_bracket(),
    ],
    "asm_arm_on_shafts": lambda: [
        parts.arm(),
        Pos(-125, 0, 3) * shaft(27.8, 20),
        Pos(125, 0, 3) * shaft(27.8, 20),
    ],
    "asm_motor_plate_on_u_bracket": lambda: [parts.u_bracket(), Pos(0, 0, 33) * parts.motor_plate()],
    "asm_spacer_stack": lambda: [Pos(0, 0, 10 * i) * parts.hex_spacer() for i in range(3)],
    "asm_pin_through_u_bracket": lambda: [
        parts.u_bracket(),
        Pos(0, 0, 20) * Rot(0, 90, 0) * shaft(5.8, 44),
    ],
    "asm_gusset_in_l_bracket": lambda: [
        parts.l_bracket(),
        Pos(3, 3, 3) * Rot(90, 0, 0) * parts.small_gusset(),
    ],
    "asm_two_gears_on_shaft": lambda: [
        shaft(7.9, 30),
        Pos(0, 0, -15) * parts.spur_gear(),
        parts.spur_gear(),
    ],
    "asm_blocks_on_plate": lambda: [
        parts.plate(),
        Pos(-25, 0, 3) * parts.bearing_block(),
        Pos(25, 0, 3) * parts.bearing_block(),
    ],
    "asm_shaft_block_collar": lambda: [
        parts.bearing_block(),
        Pos(0, 0, 25) * shaft(12.6, 50),
        Pos(0, 0, 17) * parts.shaft_collar(),
    ],
    "asm_plates_on_standoffs": lambda: [
        parts.small_plate(),
        Pos(0, 0, 14) * parts.small_plate(),
        Pos(25, 25, 7) * standoff(),
        Pos(-25, -25, 7) * standoff(),
    ],
    "asm_box_in_u_bracket": lambda: [parts.u_bracket(), Pos(0, 0, 12) * Box(30, 20, 20)],
    "asm_motor_plate_on_l_bracket": lambda: [
        parts.l_bracket(),
        Pos(-3, 15, 20) * Rot(0, 90, 0) * parts.motor_plate(),
    ],
    "asm_motor_on_plate": lambda: [
        parts.motor_plate(),
        Pos(0, 0, -23) * motor_body(),
        Pos(0, 0, 9) * shaft(5, 24),
    ],
}
