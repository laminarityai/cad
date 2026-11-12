import { describe, expect, it } from "vitest";
import { positionLabel, rangeOf, sectionOf, stepOf } from "./section";
import type { Shapes } from "./engine";

const bb: Shapes["bb"] = { xmin: -30, xmax: 30, ymin: 0, ymax: 40, zmin: 10, zmax: 80 };

describe("rangeOf", () => {
  it("is the box's side along the axis", () => {
    expect(rangeOf(bb, "x")).toEqual({ min: -30, max: 30 });
    expect(rangeOf(bb, "z")).toEqual({ min: 10, max: 80 });
  });
});

describe("sectionOf", () => {
  it("starts in the middle of the part along the axis", () => {
    expect(sectionOf({ axis: "y", at: null }, bb)).toEqual({ axis: "y", at: 20 });
    expect(sectionOf({ axis: "z", at: null }, bb)).toEqual({ axis: "z", at: 45 });
  });

  it("keeps the person's position, and holds it inside the box", () => {
    expect(sectionOf({ axis: "x", at: 12.5 }, bb)).toEqual({ axis: "x", at: 12.5 });
    expect(sectionOf({ axis: "x", at: 99 }, bb).at).toBe(30);
    expect(sectionOf({ axis: "x", at: -99 }, bb).at).toBe(-30);
  });
});

describe("stepOf", () => {
  it.each([
    [60, 0.5],
    [40, 0.2],
    [70, 0.5],
    [100, 1],
    [250, 2],
    [1000, 10],
  ])("takes a 1, 2 or 5 step near a hundredth of a %f mm side", (side, step) => {
    expect(stepOf({ min: 0, max: side })).toBe(step);
  });

  it("does not divide by a flat box", () => {
    expect(stepOf({ min: 3, max: 3 })).toBe(1);
  });
});

describe("positionLabel", () => {
  it("writes the position to the step's decimals, in mm", () => {
    expect(positionLabel(12.5, 0.5)).toBe("12.5 mm");
    expect(positionLabel(-3, 1)).toBe("-3 mm");
    expect(positionLabel(0.25, 0.05)).toBe("0.25 mm");
  });
});
