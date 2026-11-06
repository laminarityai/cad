"""Reference geometry for the edit briefs and their starting models, in build123d."""

from collections.abc import Callable

from build123d import Part

from reference import parts

Build = Callable[[], list[Part]]


def one(build: Callable[[], Part]) -> Build:
    return lambda: [build()]


STARTS: dict[str, Build] = {
    "plate": one(parts.plate),
    "l_bracket": one(parts.l_bracket),
    "motor_plate": one(parts.motor_plate),
    "spur_gear": one(parts.spur_gear),
    "hex_spacer": one(parts.hex_spacer),
    "shaft_collar": one(parts.shaft_collar),
    "gusset": one(parts.gusset),
    "u_bracket": one(parts.u_bracket),
    "bearing_block": one(parts.bearing_block),
    "arm": one(parts.arm),
}

REFERENCES: dict[str, Build] = {
    "plate_holes_outward": one(
        lambda: parts.plate(holes=((47, 17), (-47, 17), (47, -17), (-47, -17)))
    ),
    "plate_center_hole": one(lambda: parts.plate(center_hole_r=6)),
    "plate_round_corners": one(lambda: parts.plate(corner_r=5)),
    "l_bracket_longer_base": one(lambda: parts.l_bracket(base_length=60)),
    "l_bracket_inside_fillet": one(lambda: parts.l_bracket(inside_r=4)),
    "l_bracket_bigger_wall_holes": one(lambda: parts.l_bracket(wall_hole_r=3.3)),
    "motor_plate_smaller_bolt_circle": one(lambda: parts.motor_plate(bolt_circle_r=22)),
    "motor_plate_counterbore": one(lambda: parts.motor_plate(counterbore=True)),
    "motor_plate_chamfer_top": one(lambda: parts.motor_plate(chamfer_top=1)),
    "spur_gear_bigger_bore": one(lambda: parts.spur_gear(bore_r=5)),
    "spur_gear_hub": one(lambda: parts.spur_gear(hub=True)),
    "spur_gear_keyway": one(lambda: parts.spur_gear(keyway=True)),
    "hex_spacer_longer": one(lambda: parts.hex_spacer(length=16)),
    "hex_spacer_chamfer_outside": one(lambda: parts.hex_spacer(chamfer_outer=1)),
    "hex_spacer_wider": one(lambda: parts.hex_spacer(outer_r=15)),
    "shaft_collar_longer": one(lambda: parts.shaft_collar(length=14)),
    "shaft_collar_chamfer_bore": one(lambda: parts.shaft_collar(chamfer_bore=0.5)),
    "shaft_collar_clamp_slot": one(lambda: parts.shaft_collar(slot=True)),
    "gusset_smaller_hole": one(lambda: parts.gusset(hole_r=6)),
    "gusset_thicker": one(lambda: parts.gusset(thickness=6)),
    "gusset_mount_holes": one(lambda: parts.gusset(extra_holes=((35, 5), (5, 35)))),
    "u_bracket_taller": one(lambda: parts.u_bracket(height=40)),
    "u_bracket_base_holes": one(lambda: parts.u_bracket(base_holes=(-15, 15))),
    "u_bracket_raise_holes": one(lambda: parts.u_bracket(hole_z=25)),
    "bearing_block_deeper_pocket": one(lambda: parts.bearing_block(pocket_depth=10)),
    "bearing_block_four_holes": one(
        lambda: parts.bearing_block(holes=((15, 15), (-15, -15), (15, -15), (-15, 15)))
    ),
    "bearing_block_round_corners": one(lambda: parts.bearing_block(corner_r=3)),
    "arm_smaller_bores": one(lambda: parts.arm(bore_r=11)),
    "arm_fill_middle_pocket": one(lambda: parts.arm(pockets=(62.5, 187.5))),
    "arm_longer": one(lambda: parts.arm(bore_spacing=300)),
}
