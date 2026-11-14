import { describe, expect, it } from "vitest";
import type { PartWire, ShapeWire } from "@/api/types";
import { edgeFor, luminance, pickOf, type Shapes } from "./engine";
import { paintAreas } from "./where";

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

const contrast = (a: number, b: number) => {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};

/** A part of four faces, of one triangle each, in `color`, with `dark` of its faces in an area of black carbon fibre. */
function partWith(color: string, dark: number): Shapes {
  const shape: ShapeWire = {
    vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0],
    normals: [0, 0, 1, 0, 0, 1, 0, 0, 1],
    triangles: [0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2],
    triangles_per_face: [1, 1, 1, 1],
    face_types: [0, 0, 0, 0],
    edges: [0, 0, 0, 1, 0, 0],
    segments_per_edge: [1],
    edge_types: [0],
    obj_vertices: [0, 0, 0],
  };
  const part = { version: 3, id: "/variant/part", name: "part", type: "shapes", subtype: "solid", shape, state: [1, 1], color, alpha: 1 } as PartWire;
  const shapes = { version: 3, id: "/variant", name: "variant", parts: [part], bb: { xmin: 0, xmax: 1, ymin: 0, ymax: 1, zmin: 0, zmax: 0 } } as Shapes;
  return paintAreas(shapes, [{ name: "plate", colour: CARBON, faces: [0, 1, 2, 3].slice(0, dark) }]);
}

const CARBON = "#1a1a1a";

describe("the edges", () => {
  it("stand out at 4.5 to 1 or more on a light grey part and on a black carbon fibre part", () => {
    expect(contrast(edgeFor(partWith("#a6abb0", 0)), 0xa6abb0)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(edgeFor(partWith("#a6abb0", 4)), 0x1a1a1a)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(edgeFor(partWith(CARBON, 0)), 0x1a1a1a)).toBeGreaterThanOrEqual(4.5);
  });

  it("follow the colour of most of the part", () => {
    expect(edgeFor(partWith("#a6abb0", 1))).toBe(edgeFor(partWith("#a6abb0", 0)));
    expect(edgeFor(partWith("#a6abb0", 3))).toBe(edgeFor(partWith("#a6abb0", 4)));
  });
});
