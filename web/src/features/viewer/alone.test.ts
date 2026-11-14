import { describe, expect, it } from "vitest";
import type { PartWire, ShapeWire } from "@/api/types";
import { aloneOf } from "./alone";
import type { Shapes } from "./engine";
import type { Topology } from "./readout";

/** Three faces of 1, 2 and 1 triangles, and two edges of 1 and 2 segments. Edge 0 borders face 0 only and
 * edge 1 borders faces 1 and 2. */
const shape: ShapeWire = {
  vertices: [],
  normals: [],
  triangles: [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3],
  triangles_per_face: [1, 2, 1],
  face_types: [0, 0, 0],
  edges: [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3],
  segments_per_edge: [1, 2],
  edge_types: [0, 0],
  obj_vertices: [],
};

const part = { id: "/variant/part", name: "part", shape } as PartWire;
const shapes = { parts: [part] } as Shapes;
const edge = (faces: number[]) => ({ type: "LINE", length: 1, center: [0, 0, 0], direction: null, radius: null, faces });
const topology = { faces: [], edges: [edge([0]), edge([1, 2])] } as unknown as Topology;

const drawn = (faces: number[]) => {
  const [only] = aloneOf(shapes, topology, faces).parts;
  if (!only) throw new Error("no part");
  return only.shape;
};

describe("aloneOf", () => {
  it("keeps the triangles of the faces named and the edges that border them, each at its own index", () => {
    const body = drawn([1, 2]);
    expect(body.triangles).toEqual([1, 1, 1, 2, 2, 2, 3, 3, 3]);
    expect(body.triangles_per_face).toEqual([0, 2, 1]);
    expect(body.edges).toEqual([2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3]);
    expect(body.segments_per_edge).toEqual([0, 2]);
  });

  it("leaves the whole shape alone when it holds no part of the variant", () => {
    const other = { parts: [{ ...part, id: "/fit/part" }] } as Shapes;
    expect(aloneOf(other, topology, [0])).toBe(other);
  });
});
