import { describe, expect, it } from "vitest";
import { pickOf } from "./engine";

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
