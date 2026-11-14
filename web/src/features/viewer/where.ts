import type { Area, PartWire, ShapeWire } from "@/api/types";
import type { Shapes } from "./engine";

/** The faces of a part that the stress check fixed and pressed on, as face indices of the part's mesh. */
export interface Where {
  support: readonly number[];
  load: readonly number[];
}

export type Role = keyof Where;

export const PART = "/variant/part";
const ROLE_ID: Record<Role, string> = { support: "/variant/support", load: "/variant/load" };
/** Two hues that stay apart for the common colour-blindnesses and from the part's grey. */
export const ROLE_COLOUR: Record<Role, string> = { support: "#0072b2", load: "#cc79a7" };
/** The most areas the server keeps for one variant. */
const MAX_AREAS = 16;
const areaId = (n: number) => `/variant/area/${String(n)}`;

/** The ids of every part that carries faces of the variant, so a click on any of them is a click on the part. */
export const FACE_PARTS: readonly string[] = [PART, ...Object.values(ROLE_ID), ...Array.from({ length: MAX_AREAS }, (_, n) => areaId(n))];

/** Faces drawn apart from the part, in a colour of their own. */
interface Piece {
  id: string;
  name: string;
  colour: string;
  faces: ReadonlySet<number>;
}

function trianglesOf(shape: ShapeWire, faces: ReadonlySet<number>, keep: boolean): Pick<ShapeWire, "triangles" | "triangles_per_face"> {
  const triangles: number[] = [];
  const perFace: number[] = [];
  let at = 0;
  shape.triangles_per_face.forEach((count, face) => {
    const held = faces.has(face) === keep;
    if (held) for (let i = at; i < at + 3 * count; i += 1) triangles.push(shape.triangles[i] ?? 0);
    perFace.push(held ? count : 0);
    at += 3 * count;
  });
  return { triangles, triangles_per_face: perFace };
}

/** The part drawn in three: the faces in no piece in the part's own colour, and each piece as a part of its
 * own in its colour. Every piece keeps the whole part's vertices and a count for every face, empty where the
 * face is not in it, so a face's index in a piece is its index in the part and a click on any piece still
 * names the face. */
function paint(shapes: Shapes, pieces: readonly Piece[]): Shapes {
  const drawn = pieces.filter((one) => one.faces.size > 0);
  if (drawn.length === 0) return shapes;
  const [part, ...rest] = shapes.parts;
  if (part?.id !== PART) return shapes;
  const all = new Set(drawn.flatMap((one) => [...one.faces]));
  const base: PartWire = { ...part, shape: { ...part.shape, ...trianglesOf(part.shape, all, false) } };
  const overlays = drawn.map(
    ({ id, name, colour, faces }): PartWire => ({
      ...part,
      id,
      name,
      color: colour,
      state: [1, 0],
      shape: {
        ...part.shape,
        ...trianglesOf(part.shape, faces, true),
        edges: [],
        segments_per_edge: [],
        edge_types: [],
        obj_vertices: [],
      },
    }),
  );
  return { ...shapes, parts: [base, ...overlays, ...rest] };
}

/** The support and the load the stress check used, each in its role's colour. */
export function splitFaces(shapes: Shapes, where: Where): Shapes {
  return paint(
    shapes,
    (Object.keys(ROLE_ID) as Role[]).map((role) => ({ id: ROLE_ID[role], name: role, colour: ROLE_COLOUR[role], faces: new Set(where[role]) })),
  );
}

/** Each area the build code coloured, in its colour. */
export function paintAreas(shapes: Shapes, areas: readonly Area[]): Shapes {
  return paint(
    shapes,
    areas.slice(0, MAX_AREAS).map((area, n) => ({ id: areaId(n), name: area.name, colour: area.colour, faces: new Set(area.faces) })),
  );
}
