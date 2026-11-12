import { describe, expect, it, vi } from "vitest";
import { NOT_A_CHECK, readoutOf, type Measure, type Topology } from "./readout";
import type { Pick } from "./selection";

const face = (index: number): Pick => ({ kind: "face", index });
const edge = (index: number): Pick => ({ kind: "edge", index });

const plane = (area: number, center: [number, number, number], normal: [number, number, number]) => ({
  type: "PLANE",
  area,
  center,
  normal,
  radius: null,
  axis: null,
  edges: [],
});

// Faces 0 and 1 are the plate's top and bottom, face 2 the upright's side, face 3 a hole's wall,
// face 4 the top of the upright, which overlaps neither of the others.
const topology: Topology = {
  faces: [
    plane(3540, [0, 20, 5], [0, 0, 1]),
    plane(4200, [0, 20, 0], [0, 0, -1]),
    plane(300, [0, 5, 35], [0, -1, 0]),
    { type: "CYLINDER", area: 95.0332, center: [18, 10, 2.5], normal: [1, 0, 0], radius: 2.75, axis: [0, 0, 1], edges: [] },
    plane(300, [0, 2.5, 70], [0, 0, 1]),
  ],
  edges: [
    { type: "LINE", length: 60, center: [0, 0, 0], direction: [1, 0, 0], radius: null, faces: [] },
    { type: "CIRCLE", length: 17.2788, center: [18, 10, 5], direction: null, radius: 2.75, faces: [] },
    { type: "LINE", length: 40, center: [30, 20, 0], direction: [0, 1, 0], radius: null, faces: [] },
  ],
};

const nothing: Measure = () => null;

describe("readoutOf one pick", () => {
  it("gives a plane's area from the topology, exact", () => {
    expect(readoutOf([face(0)], topology, nothing)).toEqual(["Planar face", "Area 3540.00 mm²", NOT_A_CHECK]);
  });

  it("gives a round face's radius and a circle edge's, from the topology and not the mesh", () => {
    const measure = vi.fn<Measure>();
    expect(readoutOf([face(3)], topology, measure)).toEqual(["Cylindrical face", "Area 95.03 mm² · radius 2.75 mm", NOT_A_CHECK]);
    expect(readoutOf([edge(1)], topology, measure)).toEqual(["Circular edge", "Length 17.28 mm · radius 2.75 mm", NOT_A_CHECK]);
    expect(readoutOf([edge(0)], topology, measure)).toEqual(["Straight edge", "Length 60.00 mm", NOT_A_CHECK]);
    expect(measure).not.toHaveBeenCalled();
  });

  it("has nothing to say about a pick the topology does not have", () => {
    expect(readoutOf([face(40)], topology, nothing)).toBeNull();
  });
});

describe("readoutOf two parallel planes", () => {
  it("names the gap between the planes, and the closest points when they differ", () => {
    const measure: Measure = () => ({ distance: 65.28, angle: 180 });
    expect(readoutOf([face(0), face(4)], topology, measure)).toEqual([
      "Gap between the planes 65.00 mm",
      "Closest points 65.28 mm",
      NOT_A_CHECK,
    ]);
  });

  it("shows the gap alone when the closest points agree with it, and without the mesh", () => {
    expect(readoutOf([face(0), face(1)], topology, () => ({ distance: 5, angle: 180 }))).toEqual(["Gap between the planes 5.00 mm", NOT_A_CHECK]);
    expect(readoutOf([face(0), face(1)], topology, nothing)).toEqual(["Gap between the planes 5.00 mm", NOT_A_CHECK]);
  });

  it("does not put a ≈ on either number, because planes are exact", () => {
    const lines = readoutOf([face(0), face(4)], topology, () => ({ distance: 65.28, angle: 180 }));
    expect(lines?.join("\n")).not.toContain("≈");
  });
});

describe("readoutOf any other pair", () => {
  it("gives the mesh's closest distance and angle with no ≈ when both are flat or straight", () => {
    expect(readoutOf([face(0), face(2)], topology, () => ({ distance: 0, angle: 90 }))).toEqual([
      "Closest points 0.00 mm",
      "Angle 90.0°",
      NOT_A_CHECK,
    ]);
    expect(readoutOf([edge(0), edge(2)], topology, () => ({ distance: 20, angle: 90 }))?.join("\n")).not.toContain("≈");
  });

  it("starts each mesh number with ≈ when either pick is curved", () => {
    const measure: Measure = () => ({ distance: 12.3456, angle: 90 });
    for (const picks of [[face(0), face(3)], [face(3), face(0)], [edge(0), edge(1)], [face(0), edge(1)]]) {
      expect(readoutOf(picks, topology, measure)).toEqual(["Closest points ≈12.35 mm", "Angle ≈90.0°", NOT_A_CHECK]);
    }
  });

  it("leaves the angle out when the library has none", () => {
    expect(readoutOf([face(0), edge(0)], topology, () => ({ distance: 5, angle: null }))).toEqual(["Closest points 5.00 mm", NOT_A_CHECK]);
  });

  it("measures a plane against a round face with the mesh, not the plane rule", () => {
    expect(readoutOf([face(0), face(3)], topology, () => ({ distance: 2.5, angle: 90 }))?.[0]).toBe("Closest points ≈2.50 mm");
  });

  it("has no readout when the mesh cannot measure the pair", () => {
    expect(readoutOf([face(0), face(2)], topology, nothing)).toBeNull();
  });
});

describe("readoutOf what it leaves out", () => {
  it("shows nothing for no picks, three or more picks, or the whole part", () => {
    expect(readoutOf([], topology, nothing)).toBeNull();
    expect(readoutOf([face(0), face(1), face(2)], topology, () => ({ distance: 1, angle: 1 }))).toBeNull();
    expect(readoutOf([{ kind: "part" }], topology, nothing)).toBeNull();
  });

  it("always ends with the line that says it is not a check, and never says pass or fail", () => {
    const measure: Measure = () => ({ distance: 3, angle: 45 });
    for (const picks of [[face(0)], [edge(1)], [face(0), face(4)], [face(0), face(3)]]) {
      const lines = readoutOf(picks, topology, measure) ?? [];
      expect(lines[lines.length - 1]).toBe("Measured on screen. Not a check.");
      expect(lines.join(" ")).not.toMatch(/pass|fail|ok\b/i);
    }
  });
});
