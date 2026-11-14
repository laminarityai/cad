import type { PartWire } from "@/api/types";
import type { Shapes } from "./engine";
import type { Topology } from "./readout";
import { PART, trianglesOf } from "./where";

/** The part with only these faces drawn, and only the edges that border one of them. Every face and
 * every edge keeps its index, with a count of nothing where it is hidden, so a click on what is still
 * drawn names the same face or edge as on the whole part, and the colours of the areas still land on
 * their faces. Faces past the mesh are ignored. */
export function aloneOf(shapes: Shapes, topology: Topology, faces: readonly number[]): Shapes {
  const [part, ...rest] = shapes.parts;
  if (part?.id !== PART) return shapes;
  const kept = new Set(faces);
  const held = topology.edges.map((edge) => edge.faces.some((face) => kept.has(face)));
  const edges: number[] = [];
  let at = 0;
  part.shape.segments_per_edge.forEach((count, edge) => {
    if (held[edge]) edges.push(...part.shape.edges.slice(at, at + 6 * count));
    at += 6 * count;
  });
  const alone: PartWire = {
    ...part,
    shape: {
      ...part.shape,
      ...trianglesOf(part.shape, kept, true),
      edges,
      segments_per_edge: part.shape.segments_per_edge.map((count, edge) => (held[edge] ? count : 0)),
    },
  };
  return { ...shapes, parts: [alone, ...rest] };
}
