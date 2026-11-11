import { describe, expect, it } from "vitest";
import { nextSelection, summaryOf, toPicked, type Pick, type Selection } from "./selection";

const face = (index: number): Pick => ({ kind: "face", index });
const edge = (index: number): Pick => ({ kind: "edge", index });
const part: Pick = { kind: "part" };
const of = (...picks: Pick[]): Selection => ({ variantId: "v1", picks });

describe("nextSelection", () => {
  it("replaces the selection on a plain click", () => {
    expect(nextSelection(of(face(1), edge(2)), "v1", face(5), false)).toEqual(of(face(5)));
  });

  it("toggles one face or edge on shift-click", () => {
    const added = nextSelection(of(face(1)), "v1", edge(2), true);
    expect(added).toEqual(of(face(1), edge(2)));
    expect(nextSelection(added, "v1", face(1), true)).toEqual(of(edge(2)));
  });

  it("clears when the last pick is toggled off", () => {
    expect(nextSelection(of(face(1)), "v1", face(1), true)).toBeNull();
  });

  it("clears on empty space unless shift is held", () => {
    expect(nextSelection(of(face(1)), "v1", null, false)).toBeNull();
    expect(nextSelection(of(face(1)), "v1", null, true)).toEqual(of(face(1)));
  });

  it("lets the whole part replace everything, and a shift pick replace the whole part", () => {
    expect(nextSelection(of(face(1), edge(2)), "v1", part, true)).toEqual(of(part));
    expect(nextSelection(of(part), "v1", face(3), true)).toEqual(of(face(3)));
  });

  it("starts over when the selection was for another variant", () => {
    expect(nextSelection({ variantId: "v0", picks: [face(1)] }, "v1", face(2), true)).toEqual(of(face(2)));
  });
});

describe("what the person sees and what is sent", () => {
  it("words the selection by what it holds", () => {
    expect(summaryOf(of(face(1)))).toBe("1 face");
    expect(summaryOf(of(face(1), face(2), edge(7)))).toBe("2 faces, 1 edge");
    expect(summaryOf(of(edge(3), edge(4)))).toBe("2 edges");
    expect(summaryOf(of(part))).toBe("Whole part");
  });

  it("sends the BREP numbers the viewer picked, in order", () => {
    expect(toPicked(of(face(9), edge(4), face(2)))).toEqual({ variant_id: "v1", faces: [2, 9], edges: [4], part: false });
    expect(toPicked(of(part))).toEqual({ variant_id: "v1", faces: [], edges: [], part: true });
  });
});
