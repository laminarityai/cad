import { describe, expect, it } from "vitest";
import type { Shapes } from "./engine";
import { quaternionOf, SUPPLIED_COLOUR, withSupplied } from "./supplied";

const box = (id: string, bb: Shapes["bb"]) =>
  ({
    id: "/variant",
    name: "variant",
    loc: [[0, 0, 0], [0, 0, 0, 1]],
    parts: [{ id: `${id}/part`, name: "part", color: "#a6abb0", alpha: 1, loc: [[0, 0, 0], [0, 0, 0, 1]] }],
    bb,
  }) as unknown as Shapes;

const plate = box("/variant", { xmin: -50, xmax: 50, ymin: -30, ymax: 30, zmin: 0, zmax: 5 });
const wheel = box("/variant", { xmin: -10, xmax: 10, ymin: -10, ymax: 10, zmin: 0, zmax: 8 });

describe("quaternionOf", () => {
  it("turns as build123d's Location does: about X, then Y, then Z", () => {
    // build123d: Location((1, 2, 3), (10, 20, 30)).wrapped quaternion, read in the sandbox image.
    const [x, y, z, w] = quaternionOf([10, 20, 30]);
    expect(x).toBeCloseTo(0.12767944, 7);
    expect(y).toBeCloseTo(0.14487813, 7);
    expect(z).toBeCloseTo(0.26853582, 7);
    expect(w).toBeCloseTo(0.94371436, 7);
    quaternionOf([90, 90, 0]).forEach((one) => {
      expect(one).toBeCloseTo(0.5, 7);
    });
  });
});

describe("withSupplied", () => {
  it("draws a copy of the part at each placement in the supplied colour and widens the box to hold them", () => {
    const placements = [
      { at: [-40, -25, 5] as [number, number, number], rotate: [0, 0, 0] as [number, number, number] },
      { at: [40, 25, 5] as [number, number, number], rotate: [90, 0, 0] as [number, number, number] },
    ];
    const drawn = withSupplied(plate, [{ partId: "part-w", shapes: wheel, placements }]);
    expect(drawn.parts.map((one) => one.id)).toEqual(["/variant/part", "/supplied/part-w/0/variant/part", "/supplied/part-w/1/variant/part"]);
    const [, first, second] = drawn.parts;
    expect(first?.color).toBe(SUPPLIED_COLOUR);
    expect(first?.loc[0]).toEqual([-40, -25, 5]);
    expect(second?.loc[1][0]).toBeCloseTo(Math.SQRT1_2, 7);
    // Turned 90 degrees about X, the wheel's 8 mm height lies along -Y from y = 25, and its 10 mm radius along Z.
    expect(drawn.bb.xmin).toBe(-50);
    expect(drawn.bb.ymin).toBe(-35);
    expect(drawn.bb.zmin).toBeCloseTo(-5, 7);
    expect(drawn.bb.zmax).toBeCloseTo(15, 7);
  });

  it("hands back the body unchanged when the build placed nothing", () => {
    expect(withSupplied(plate, [])).toBe(plate);
  });
});
