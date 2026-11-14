import { describe, expect, it } from "vitest";
import type { PartWire, ShapeWire } from "@/api/types";
import type { Shapes } from "./engine";
import { FACE_PARTS, ROLE_COLOUR, paintAreas, splitFaces } from "./where";

/** Four faces of 1, 2, 0 and 1 triangles, whose triangle k is the vertices (k, k, k). */
const shape: ShapeWire = {
  vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0],
  normals: [0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1],
  triangles: [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3],
  triangles_per_face: [1, 2, 0, 1],
  face_types: [0, 0, 0, 0],
  edges: [0, 0, 0, 1, 0, 0],
  segments_per_edge: [1],
  edge_types: [0],
  obj_vertices: [0, 0, 0],
};

const part: PartWire = {
  version: 3,
  id: "/variant/part",
  name: "part",
  type: "shapes",
  subtype: "solid",
  shape,
  state: [1, 1],
  color: "#a6abb0",
  alpha: 1,
  texture: null,
  loc: [[0, 0, 0], [0, 0, 0, 1]],
  renderback: false,
  accuracy: 0.01,
  bb: null,
};

const shapes = {
  version: 3,
  id: "/variant",
  name: "variant",
  parts: [part],
  loc: [[0, 0, 0], [0, 0, 0, 1]],
  normal_len: 0,
  bb: { xmin: 0, xmax: 1, ymin: 0, ymax: 1, zmin: 0, zmax: 0 },
} as Shapes;

const byId = (split: Shapes, id: string) => split.parts.find((one) => one.id === id);

describe("splitFaces", () => {
  it("draws the support and the load as parts of their own and leaves every other face in the part", () => {
    const split = splitFaces(shapes, { support: [1], load: [3] });
    expect(split.parts.map((one) => one.id)).toEqual(["/variant/part", "/variant/support", "/variant/load"]);
    expect(byId(split, "/variant/part")?.shape.triangles).toEqual([0, 0, 0]);
    expect(byId(split, "/variant/part")?.shape.triangles_per_face).toEqual([1, 0, 0, 0]);
    expect(byId(split, "/variant/support")?.shape.triangles).toEqual([1, 1, 1, 2, 2, 2]);
    expect(byId(split, "/variant/support")?.shape.triangles_per_face).toEqual([0, 2, 0, 0]);
    expect(byId(split, "/variant/load")?.shape.triangles).toEqual([3, 3, 3]);
    expect(byId(split, "/variant/load")?.shape.triangles_per_face).toEqual([0, 0, 0, 1]);
  });

  it("keeps each face's index, the vertices and the part's edges, so a click still names the face", () => {
    const split = splitFaces(shapes, { support: [1], load: [3] });
    for (const one of split.parts) {
      expect(one.shape.triangles_per_face).toHaveLength(4);
      expect(one.shape.vertices).toBe(shape.vertices);
    }
    expect(byId(split, "/variant/part")?.shape.edges).toEqual(shape.edges);
    expect(byId(split, "/variant/support")?.shape.edges).toEqual([]);
    expect(byId(split, "/variant/support")?.shape.segments_per_edge).toEqual([]);
  });

  it("gives the two roles their own colours and leaves the part's", () => {
    const split = splitFaces(shapes, { support: [0], load: [3] });
    expect(byId(split, "/variant/part")?.color).toBe("#a6abb0");
    expect(byId(split, "/variant/support")?.color).toBe(ROLE_COLOUR.support);
    expect(byId(split, "/variant/load")?.color).toBe(ROLE_COLOUR.load);
    expect(ROLE_COLOUR.support).not.toBe(ROLE_COLOUR.load);
  });

  it("draws no part for a role with no faces, and the shapes as they were when neither has any", () => {
    expect(splitFaces(shapes, { support: [0], load: [] }).parts.map((one) => one.id)).toEqual(["/variant/part", "/variant/support"]);
    expect(splitFaces(shapes, { support: [], load: [] })).toBe(shapes);
  });

  it("does not mutate the shapes it was given", () => {
    const before = JSON.stringify(shapes);
    splitFaces(shapes, { support: [1], load: [3] });
    expect(JSON.stringify(shapes)).toBe(before);
  });
});

describe("paintAreas", () => {
  it("draws each area as a part of its own in its colour and leaves the faces in none grey", () => {
    const painted = paintAreas(shapes, [
      { name: "steel gear", colour: "#808080", faces: [0, 1] },
      { name: "carbon plate", colour: "#000000", faces: [3] },
    ]);
    expect(painted.parts.map((one) => [one.id, one.name, one.color])).toEqual([
      ["/variant/part", "part", "#a6abb0"],
      ["/variant/area/0", "steel gear", "#808080"],
      ["/variant/area/1", "carbon plate", "#000000"],
    ]);
    expect(byId(painted, "/variant/area/0")?.shape.triangles_per_face).toEqual([1, 2, 0, 0]);
    expect(byId(painted, "/variant/part")?.shape.triangles_per_face).toEqual([0, 0, 0, 0]);
    expect(byId(painted, "/variant/part")?.shape.edges).toEqual(shape.edges);
  });

  it("counts a click on an area as a click on the part", () => {
    const painted = paintAreas(shapes, [{ name: "grip", colour: "#1a1a1a", faces: [1] }]);
    for (const one of painted.parts) expect(FACE_PARTS).toContain(one.id);
  });

  it("leaves the shapes as they were when the build code coloured nothing", () => {
    expect(paintAreas(shapes, [])).toBe(shapes);
  });
});
