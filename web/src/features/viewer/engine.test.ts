import { describe, expect, it } from "vitest";
import { EDGE, pickOf } from "./engine";

describe("pickOf", () => {
  it("names a face by its index whichever piece of the part it was drawn in", () => {
    for (const piece of ["part", "support", "load"]) {
      expect(pickOf(`/variant/${piece}/faces/faces_12`)).toEqual({ kind: "face", index: 12 });
    }
  });

  it("names an edge, and nothing else", () => {
    expect(pickOf("/variant/part/edges/edges_3")).toEqual({ kind: "edge", index: 3 });
    expect(pickOf("/fit/variant/part/faces/faces_1")).toBeNull();
    expect(pickOf("/variant/other/faces/faces_1")).toBeNull();
    expect(pickOf("")).toBeNull();
  });
});

describe("the edges", () => {
  it("stand out from the neutral grey part, whatever the theme, at 4.5 to 1 or more", () => {
    const luminance = (rgb: number) =>
      [
        [16, 0.2126],
        [8, 0.7152],
        [0, 0.0722],
      ].reduce((sum, [shift = 0, weight = 0]) => {
        const c = ((rgb >> shift) & 0xff) / 255;
        return sum + weight * (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
      }, 0);
    const [edge, grey] = [luminance(EDGE), luminance(0xa6abb0)];
    expect((Math.max(edge, grey) + 0.05) / (Math.min(edge, grey) + 0.05)).toBeGreaterThanOrEqual(4.5);
  });
});
