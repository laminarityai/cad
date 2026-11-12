import { describe, expect, it } from "vitest";
import { dimensionLines, pointsOf, toScreen, type Extents } from "./dimensions";

const bb = { xmin: -30, xmax: 30, ymin: 0, ymax: 40, zmin: 0, zmax: 70 };
const extents: Extents = { x: "60 mm", y: "40 mm", z: "70 mm" };

describe("dimensionLines", () => {
  it("draws one line per axis along an edge of the box, each with the check's label", () => {
    const lines = dimensionLines(extents, bb);
    expect(lines.map((one) => [one.axis, one.label])).toEqual([
      ["x", "60 mm"],
      ["y", "40 mm"],
      ["z", "70 mm"],
    ]);
    expect(lines.map((one) => one.edge)).toEqual([
      [[-30, 40, 0], [30, 40, 0]],
      [[30, 0, 0], [30, 40, 0]],
      [[30, 0, 0], [30, 0, 70]],
    ]);
  });

  it("stands each line off its edge by 12% of the largest side, outward from the box", () => {
    const [x, y, z] = dimensionLines(extents, bb);
    expect(x?.from).toEqual([-30, 40 + 8.4, -8.4]);
    expect(y?.to).toEqual([30 + 8.4, 40, -8.4]);
    expect(z?.from).toEqual([30 + 8.4, -8.4, 0]);
  });

  it("labels with the check's words whatever the box measures", () => {
    const lines = dimensionLines({ x: "1 mm", y: "2 mm", z: "3 mm" }, bb);
    expect(lines.map((one) => one.label)).toEqual(["1 mm", "2 mm", "3 mm"]);
  });

  it("draws nothing for a box that is not a number", () => {
    expect(dimensionLines(extents, { ...bb, xmax: Number.NaN })).toEqual([]);
  });

  it("lists four points to a line for the engine to project", () => {
    expect(pointsOf(dimensionLines(extents, bb))).toHaveLength(12);
  });
});

describe("toScreen", () => {
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  // An orthographic camera looking down -z, with a 100 by 50 view volume.
  const ortho = [1 / 50, 0, 0, 0, 0, 1 / 25, 0, 0, 0, 0, -0.01, 0, 0, 0, 0, 1];

  it("puts the middle of the view in the middle of the canvas and flips y", () => {
    expect(toScreen(identity, ortho, [0, 0, 0], 200, 100)).toEqual({ x: 100, y: 50 });
    expect(toScreen(identity, ortho, [50, 25, 0], 200, 100)).toEqual({ x: 200, y: 0 });
  });

  it("gives null for a point behind a perspective camera", () => {
    const perspective = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, -1, 0, 0, -1, 0];
    expect(toScreen(identity, perspective, [0, 0, 5], 200, 100)).toBeNull();
    expect(toScreen(identity, perspective, [0, 0, -5], 200, 100)).not.toBeNull();
  });
});
